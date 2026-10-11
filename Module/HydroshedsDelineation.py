"""
HydroshedsDelineation.py
========================
Step i of the screening methodology: for each dam, find the BasinATLAS
level-12 sub-basin that contains it, trace the upstream sub-basins and
river network, identify upstream portfolio dams, and export the per-dam and
merged GeoPackages.

Imported by RunScreening.py; not meant to be run on its own.

Reuses the approach of the sibling projects:
  - Watershed_generator/ExtractBasinAtlasAttributesAtDamSite.py
    (point-in-polygon sub-basin match, NEXT_DOWN BFS, same-sub-basin dam order)
  - Extract_Downstream_River_Course/ExtractDownstreamRiverCourse.py
    (snap dam to nearest HydroRIVERS reach, follow NEXT_DOWN to the outlet)

Memory/speed: the global level-12 layer (1.03 M polygons) is never loaded
in full. Only the 4 graph columns are read once (no geometry); polygons are
fetched per dam through a bbox query, or by feature id for the watershed.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from shapely.geometry import Point

# ── Paths ─────────────────────────────────────────────────────────────────────

GIS_DIR = Path("/Users/filou/MyProjects/MyGISProjects/Resources/Maps and data")
BASIN_GDB = GIS_DIR / "BasinATLAS" / "BasinATLAS_v10.gdb"
BASIN_LAYER = "BasinATLAS_v10_lev12"
RIVERS_SHP = GIS_DIR / "HydroRIVERS" / "HydroRIVERS_v10_shp" / "HydroRIVERS_v10.shp"

# ── Parameters ────────────────────────────────────────────────────────────────

SNAP_RADIUS_M = 2000.0        # dam must have a HydroRIVERS reach within this distance
SAME_BASIN_AREA_TOL = 0.05    # two dams in one sub-basin: areas closer than this -> order unknown
MAX_CHAIN_STEPS = 200_000     # safety cap against cyclic NEXT_DOWN data
METRIC_CRS = "EPSG:4087"      # World Equidistant Cylindrical, for snap distances only

LAYERS = ["Dams", "Watershed", "Sub_basins", "River_Networks", "River_Downstream"]
# Merged-layer key that identifies a unique feature ("avoid duplication")
MERGE_KEYS = {"Dams": "Dam_ID", "Watershed": "Dam_ID", "Sub_basins": "HYBAS_ID",
              "River_Networks": "HYRIV_ID", "River_Downstream": "HYRIV_ID"}


# ── Sub-basin graph ───────────────────────────────────────────────────────────

def load_basin_graph():
    """Read HYBAS_ID/NEXT_DOWN/areas once (no geometry).

    Returns (fid_of, children): HYBAS_ID -> feature id in the GDB layer, and
    HYBAS_ID -> list of sub-basins draining directly into it."""
    graph = pyogrio.read_dataframe(
        BASIN_GDB, layer=BASIN_LAYER,
        columns=["HYBAS_ID", "NEXT_DOWN"], read_geometry=False, fid_as_index=True,
    )
    fid_of = dict(zip(graph["HYBAS_ID"].astype("int64"), graph.index))
    children = (graph.assign(HYBAS_ID=graph["HYBAS_ID"].astype("int64"))
                .groupby("NEXT_DOWN")["HYBAS_ID"].apply(list).to_dict())
    return fid_of, children


def locate_subbasin(lat, lon):
    """Level-12 sub-basin containing the point, as a one-row GeoDataFrame
    (all 296 attributes + geometry), or None if the point is outside."""
    cand = pyogrio.read_dataframe(BASIN_GDB, layer=BASIN_LAYER, bbox=(lon, lat, lon, lat))
    if cand.empty:
        return None
    pt = Point(lon, lat)
    hit = cand[cand.contains(pt)]
    if hit.empty:                       # dam exactly on a polygon edge
        hit = cand[cand.intersects(pt)]
    return hit.iloc[[0]] if len(hit) else None


def upstream_subbasins(hybas_id, children):
    """The sub-basin itself plus every sub-basin upstream of it (BFS on NEXT_DOWN)."""
    found = {hybas_id}
    queue = [hybas_id]
    while queue:
        for up in children.get(queue.pop(), []):
            if up not in found:
                found.add(up)
                queue.append(up)
    return found


# ── Upstream dams ─────────────────────────────────────────────────────────────

def assign_upstream_dams(dams, children):
    """dams: DataFrame with Dam_ID, HYBAS_ID (NaN if unmatched), Catchment_km2.

    Returns {Dam_ID: (upstream_ids, ambiguous_ids)}.
      - dams in a strictly upstream sub-basin are upstream;
      - dams sharing the sub-basin are ordered by Catchment_km2 (smaller =
        upstream); if either area is missing, or the two differ by less than
        SAME_BASIN_AREA_TOL, the order is unknown and the dam is returned in
        `ambiguous_ids` instead (not counted as upstream)."""
    by_basin = {}
    for dam_id, hybas, area in zip(dams["Dam_ID"], dams["HYBAS_ID"], dams["Catchment_km2"]):
        if pd.notna(hybas):
            by_basin.setdefault(int(hybas), []).append((dam_id, area))

    result = {}
    for dam_id, hybas, own_area in zip(dams["Dam_ID"], dams["HYBAS_ID"], dams["Catchment_km2"]):
        if pd.isna(hybas):
            result[dam_id] = ([], [])
            continue
        hybas = int(hybas)
        ups = [d for b in upstream_subbasins(hybas, children) - {hybas}
               for d, _ in by_basin.get(b, [])]
        ambiguous = []
        for other_id, area in by_basin[hybas]:
            if other_id == dam_id:
                continue
            if (pd.isna(area) or pd.isna(own_area) or area == 0 or own_area == 0
                    or abs(area - own_area) <= SAME_BASIN_AREA_TOL * max(area, own_area)):
                ambiguous.append(other_id)
            elif area < own_area:
                ups.append(other_id)
        result[dam_id] = (sorted(ups), sorted(ambiguous))
    return result


# ── HydroRIVERS ───────────────────────────────────────────────────────────────

def load_river_graph():
    """HYRIV_ID -> NEXT_DOWN lookup and HYRIV_ID -> shapefile feature id (no geometry)."""
    rivers = pyogrio.read_dataframe(
        RIVERS_SHP, columns=["HYRIV_ID", "NEXT_DOWN"], read_geometry=False, fid_as_index=True,
    )
    return rivers.set_index("HYRIV_ID")["NEXT_DOWN"], pd.Series(rivers.index, index=rivers["HYRIV_ID"])


def snap_to_reach(lat, lon, radius_m=SNAP_RADIUS_M):
    """Nearest HydroRIVERS reach within radius_m of the dam: (HYRIV_ID, distance_m)
    or (None, None)."""
    pad = radius_m / 111_000 * 1.5      # generous degree pad around the point
    cand = pyogrio.read_dataframe(RIVERS_SHP, columns=["HYRIV_ID"],
                                  bbox=(lon - pad, lat - pad, lon + pad, lat + pad))
    if cand.empty:
        return None, None
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(METRIC_CRS).iloc[0]
    dist = cand.to_crs(METRIC_CRS).distance(pt)
    if dist.min() > radius_m:
        return None, None
    best = dist.idxmin()
    return int(cand.loc[best, "HYRIV_ID"]), float(dist.min())


def trace_downstream(next_down, start_id):
    """Follow NEXT_DOWN from start_id to the outlet. Returns (chain, status)."""
    chain, seen, current = [], set(), start_id
    for _ in range(MAX_CHAIN_STEPS):
        if current not in next_down.index:
            return chain, "BROKEN_CHAIN"
        if current in seen:
            return chain, "CYCLE_DETECTED"
        chain.append(current)
        seen.add(current)
        current = next_down.loc[current]
        if current == 0:
            return chain, "REACHED_OUTLET"
    return chain, "MAX_STEPS_EXCEEDED"


# ── Per-dam export ────────────────────────────────────────────────────────────

def _write_layer(gdf, path, layer):
    """Write a layer; skip empty frames so no schema-less layer is created."""
    if len(gdf):
        pyogrio.write_dataframe(gdf, path, layer=layer, driver="GPKG")


def export_dam(dam, upstream_dams, dams_all, fid_of, children, river_next_down, river_fid, gpkg_path):
    """Build and write the 5 layers of <Dam_ID>.gpkg. Returns a diagnostics dict.

    dam: row (Series) of the portfolio table with HYBAS_ID/Latitude/Longitude.
    upstream_dams: list of Dam_IDs upstream of this dam.
    dams_all: portfolio table indexed by Dam_ID (for upstream-dam points)."""
    dam_id = dam["Dam_ID"]
    ids = sorted(upstream_subbasins(int(dam["HYBAS_ID"]), children))
    subbasins = pyogrio.read_dataframe(
        BASIN_GDB, layer=BASIN_LAYER, fids=[fid_of[i] for i in ids],
        columns=["HYBAS_ID", "NEXT_DOWN", "SUB_AREA", "UP_AREA"])
    subbasins.insert(0, "Dam_ID", dam_id)

    outline = shapely.union_all(subbasins.geometry.values)
    watershed = gpd.GeoDataFrame(
        {"Dam_ID": [dam_id], "Nb_Sub_Basins": [len(subbasins)],
         "Area_km2": [round(subbasins["SUB_AREA"].sum(), 1)]},
        geometry=[outline], crs=subbasins.crs)

    members = dams_all.loc[[dam_id] + upstream_dams]
    dams_layer = gpd.GeoDataFrame(
        {"Dam_ID": members["Dam_ID"].values, "Dam_Name": members["Dam_Name"].values,
         "Reservoir_hm3": members["Reservoir_hm3"].values,
         "Role": ["dam"] + ["upstream"] * len(upstream_dams)},
        geometry=gpd.points_from_xy(members["Longitude"], members["Latitude"]), crs="EPSG:4326")

    # River network inside the watershed: reaches whose representative point is within it
    rivers = pyogrio.read_dataframe(RIVERS_SHP, bbox=tuple(outline.bounds))
    pts = rivers.geometry.representative_point()
    network = rivers[shapely.contains_xy(outline, pts.x.values, pts.y.values)].copy()
    network.insert(0, "Dam_ID", dam_id)

    # River downstream: snap to nearest reach, follow NEXT_DOWN to the outlet
    start_id, snap_m = snap_to_reach(dam["Latitude"], dam["Longitude"])
    downstream, status = gpd.GeoDataFrame(), "NO_REACH_WITHIN_RADIUS"
    if start_id is not None:
        chain, status = trace_downstream(river_next_down, start_id)
        downstream = pyogrio.read_dataframe(RIVERS_SHP, fids=[int(river_fid.loc[c]) for c in chain])
        downstream["FLOW_ORDER"] = downstream["HYRIV_ID"].map({c: i for i, c in enumerate(chain)})
        downstream = downstream.sort_values("FLOW_ORDER").reset_index(drop=True)
        downstream.insert(0, "Dam_ID", dam_id)

    gpkg_path = Path(gpkg_path)
    gpkg_path.unlink(missing_ok=True)
    for name, gdf in zip(LAYERS, [dams_layer, watershed, subbasins, network, downstream]):
        _write_layer(gdf, gpkg_path, name)

    return {"Dam_ID": dam_id, "HYBAS_ID": int(dam["HYBAS_ID"]), "n_sub_basins": len(subbasins),
            "n_upstream_dams": len(upstream_dams), "n_river_reaches": len(network),
            "start_HYRIV_ID": start_id,
            "snap_distance_m": None if snap_m is None else round(snap_m, 1),
            "n_downstream_reaches": len(downstream), "downstream_status": status}


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_gpkgs(folder, out_name="All_Dams.gpkg"):
    """Merge every <Dam_ID>.gpkg in folder into All_Dams.gpkg, same 5 layers,
    keeping one feature per Dam_ID (Dams, Watershed), HYBAS_ID (Sub_basins) or
    HYRIV_ID (River_*), since sub-basins and reaches are shared by nested
    watersheds. Per-dam attribution of shared features stays in the
    individual files and in the Watershed layer."""
    folder = Path(folder)
    out = folder / out_name
    out.unlink(missing_ok=True)
    files = sorted(p for p in folder.glob("*.gpkg") if p.name != out_name)

    for layer in LAYERS:
        parts = [gpd.read_file(f, layer=layer) for f in files if layer in pyogrio.list_layers(f)[:, 0]]
        if not parts:
            continue
        merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
        merged = merged.drop_duplicates(subset=MERGE_KEYS[layer])
        # Role / Dam_ID / FLOW_ORDER describe one dam's view and mean nothing on a shared feature
        drop = {"Dams": ["Role"], "Watershed": []}.get(layer, ["Dam_ID", "FLOW_ORDER"])
        _write_layer(merged.drop(columns=drop, errors="ignore"), out, layer)
    return out
