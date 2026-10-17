"""
LandslideHazard.py
==================
Adds a 'Landslide_hazard' layer to every per-dam GeoPackage: the qualitative global landslide hazard
map (ThinkHazard! / GFDRR and The World Bank, ~1 km, 60 deg S to 72 deg N) clipped to the dam's
watershed. Identical in the HydroSHEDS and TDX-Hydro versions of the tool.

The raster (LS_TH_COG.tif) holds 1 = very low, 2 = low, 3 = medium, 4 = high hazard and 255 for lakes,
oceans and areas outside the map. Pixels are grouped by class, polygonised and cut with the watershed
outline, so the layer has at most four polygons per dam (one per class present):

    Dam_ID, Hazard_Level (1-4), Hazard_Class, Area_km2, Share_pct (of the watershed area)

Unmapped parts (255 or outside the raster) are not drawn, so the shares can add up to less than 100 %.
The four shares are also written to the output CSV (columns Landslide_<class>_pct, see shares()).
Areas are computed in an equal-area projection. The map is meant for regional-scale decisions, not for
site-specific assessment (Arup, 2020).

Imported by RunScreening.py.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely
from rasterio.features import geometry_mask, shapes
from rasterio.windows import from_bounds
from shapely.geometry import shape

HAZARD_TIF = Path("/Users/filou/Library/Mobile Documents/com~apple~CloudDocs/"
                  "GlobalData/Global landslide hazard map/LS_TH_COG.tif")
LAYER = "Landslide_hazard"
CLASSES = {1: "Very low", 2: "Low", 3: "Medium", 4: "High"}
NO_DATA = 255
COLUMNS = {1: "Landslide_VeryLow_pct", 2: "Landslide_Low_pct", 3: "Landslide_Medium_pct", 4: "Landslide_High_pct"}
EQUAL_AREA_CRS = "EPSG:6933"      # World Cylindrical Equal Area, for areas only


def open_map():
    """Open the hazard raster. The map is kept in iCloud Drive, which macOS only lets an app read once it
    has been given access; without it the open fails with 'Operation not permitted'."""
    try:
        return rasterio.open(HAZARD_TIF)
    except rasterio.errors.RasterioIOError as error:
        if "not permitted" in str(error).lower():
            raise SystemExit(
                f"macOS does not let this program read the landslide hazard map:\n  {HAZARD_TIF}\n"
                "It is stored in iCloud Drive. Allow the app you run Python from (Terminal, iTerm, VS Code, PyCharm, ...)\n"
                "to use it: System Settings > Privacy & Security > Files and Folders > that app > iCloud Drive\n"
                "(or add the app under Full Disk Access), restart the app and run again. Alternatively copy the\n"
                "file to a normal folder and change HAZARD_TIF in Module/LandslideHazard.py.") from None
        raise


def has_layer(gpkg_path):
    p = Path(gpkg_path)
    return p.exists() and LAYER in pyogrio.list_layers(p)[:, 0]


def _polygonal(geom):
    """The polygon parts of an intersection result (it can also hold lines or points)."""
    if geom.is_empty or geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def hazard_polygons(watershed, dam_id):
    """GeoDataFrame of the hazard classes inside the watershed (shapely polygon, EPSG:4326), or an
    empty one when the watershed is outside the map."""
    if not watershed.is_valid:
        watershed = shapely.make_valid(watershed)
    with open_map() as src:
        win = from_bounds(*watershed.bounds, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=win, boundless=True, fill_value=NO_DATA)
        transform = src.window_transform(win)
    classes = np.where(np.isin(data, list(CLASSES)), data, 0).astype("uint8")
    if not classes.any():
        return gpd.GeoDataFrame({"Dam_ID": []}, geometry=[], crs="EPSG:4326")
    pieces = {}
    for geo, value in shapes(classes, mask=classes > 0, transform=transform, connectivity=4):
        pieces.setdefault(int(value), []).append(shape(geo))
    rows = []
    for level in sorted(pieces):
        clipped = _polygonal(shapely.union_all(pieces[level]).intersection(watershed))
        if not clipped.is_empty:
            rows.append((level, clipped))
    if not rows:
        return gpd.GeoDataFrame({"Dam_ID": []}, geometry=[], crs="EPSG:4326")
    out = gpd.GeoDataFrame({"Dam_ID": dam_id, "Hazard_Level": [r[0] for r in rows],
                            "Hazard_Class": [CLASSES[r[0]] for r in rows]},
                           geometry=[r[1] for r in rows], crs="EPSG:4326")
    area = out.to_crs(EQUAL_AREA_CRS).area / 1e6
    total = gpd.GeoSeries([watershed], crs="EPSG:4326").to_crs(EQUAL_AREA_CRS).area.iloc[0] / 1e6
    out["Area_km2"] = area.round(3).to_numpy()
    out["Share_pct"] = (100 * area / total).round(2).to_numpy()
    return out


def add_layer(gpkg_path):
    """Compute and write the Landslide_hazard layer of one dam from its Watershed layer."""
    ws = gpd.read_file(gpkg_path, layer="Watershed")
    layer = hazard_polygons(ws.geometry.iloc[0], ws["Dam_ID"].iloc[0])
    if len(layer):
        pyogrio.write_dataframe(layer, gpkg_path, layer=LAYER, driver="GPKG")
    return layer


def ensure_layers(folder, dam_ids, force=False):
    """Add the layer to every dam GeoPackage of the folder that lacks it (all of them with force).
    Returns the number of GeoPackages processed."""
    todo = [d for d in dam_ids if (Path(folder) / f"{d}.gpkg").exists()
            and (force or not has_layer(Path(folder) / f"{d}.gpkg"))]
    if todo:
        open_map().close()                  # fail at once, with an explanation, if the map cannot be read
    for i, dam_id in enumerate(todo, 1):
        layer = add_layer(Path(folder) / f"{dam_id}.gpkg")
        shares = ", ".join(f"{r.Hazard_Class} {r.Share_pct:.0f}%" for r in layer.itertuples()) or "outside the map"
        print(f"  [{i}/{len(todo)}] {dam_id}: {shares}")
    return len(todo)


def shares(folder, dam_ids):
    """Share (%) of each dam's watershed in each hazard class, read from the Landslide_hazard layers:
    a DataFrame indexed by Dam_ID with the COLUMNS. A class absent from a mapped watershed is 0; dams
    without a layer (no watershed, or outside the map) are missing."""
    rows = {}
    for dam_id in dam_ids:
        path = Path(folder) / f"{dam_id}.gpkg"
        if not has_layer(path):
            continue
        layer = pyogrio.read_dataframe(path, layer=LAYER, read_geometry=False).set_index("Hazard_Level")["Share_pct"]
        rows[dam_id] = {col: float(layer.get(level, 0.0)) for level, col in COLUMNS.items()}
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(COLUMNS.values()))
