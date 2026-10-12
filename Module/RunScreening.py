"""
RunScreening.py
===============
Reservoir sedimentation risk screening, end to end (see the methodological
note, "reservoir sedimentation methodological note_HydroSheds").

Input   Data/<portfolio>.csv   (picked in a file dialog) with columns
        Dam_ID, Dam_Name, Latitude, Longitude, Construction_Year,
        Reservoir_hm3, Catchment_km2
Output  Output/<portfolio>_Hydrosheds_Scen<#>_SDR_<..>_TE_<..>.csv   input + calculated + 296 HydroATLAS columns
        Output/<same name>_diagnostics.csv             per-dam delineation log + the scenario parameters
        Plot/<same name>.png                           screening diagram of the scenario
        Output/<portfolio>_Watershed/<Dam_ID>.gpkg     Dams, Watershed, Sub_basins, River_Networks,
                                                       River_Downstream, Landslide_hazard
        Output/<portfolio>_Watershed/All_Dams.gpkg     the same 6 layers merged, no duplicates
        <#> is the next free scenario number of the portfolio. The watersheds do not depend on the
        scenario and are reused.

Scenario: one sediment delivery ratio (SDR: low Diodato, high Gourfi, or user-defined a x A^b)
and one trapping efficiency (TE: low, medium, high), asked for in the terminal or given as
--sdr/--a/--b/--te (see Scenario.py).

Resume: a <Dam_ID>.gpkg that already exists is not rebuilt. Delete the
<portfolio>_Watershed folder to force a full rebuild.

Run:  uv run python Module/RunScreening.py [portfolio.csv] [--sdr low|high|user [--a A --b B]]
                                            [--te low|medium|high] [--scen-number N] [--density KG_M3]
      no csv argument opens the file dialog; without --sdr/--te/--density you are asked
      (Enter = low / low / 1200 kg/m3)
"""

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import pandas as pd
import pyogrio

import HydroshedsDelineation as hd
import LandslideHazard
import ScreeningPlots
import Scenario
import SedimentationCalcs as calcs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
OUTPUT_DIR = PROJECT_ROOT / "Output"

INPUT_COLS = ["Dam_ID", "Dam_Name", "Latitude", "Longitude",
              "Construction_Year", "Reservoir_hm3", "Catchment_km2"]


def parse_args():
    ap = argparse.ArgumentParser(description="Reservoir sedimentation risk screening.")
    ap.add_argument("portfolio", nargs="?", help="CSV path or filename in Data/ (default: file dialog)")
    Scenario.add_arguments(ap)
    ap.add_argument("--density", type=float,
                    help=f"bulk density of deposited sediment, kg/m3 (default {calcs.DEFAULT_DENSITY_KG_M3:g})")
    return ap.parse_args()


def ask_density():
    default = calcs.DEFAULT_DENSITY_KG_M3
    while True:
        raw = input(f"Sediment bulk density [kg/m3, default {default:g}]: ").strip()
        if not raw:
            return default
        try:
            if float(raw) > 0:
                return float(raw)
        except ValueError:
            pass
        print("  Please enter a positive number, or press Enter for the default.")


def pick_csv(portfolio):
    if portfolio:                       # skips the dialog
        arg = Path(portfolio)
        return arg if arg.exists() else DATA_DIR / arg
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    chosen = filedialog.askopenfilename(title="Select the portfolio CSV", initialdir=DATA_DIR,
                                        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    root.destroy()
    if not chosen:
        raise SystemExit("No file selected — exiting.")
    return Path(chosen)


def main():
    args = parse_args()
    csv_path = pick_csv(args.portfolio)
    density = args.density if args.density else (
        ask_density() if sys.stdin.isatty() else calcs.DEFAULT_DENSITY_KG_M3)
    scen = Scenario.from_args(args)
    stem = csv_path.stem
    base = f"{stem}_Hydrosheds"
    number = args.scen_number or Scenario.next_number(OUTPUT_DIR, base)
    run_name = f"{base}_Scen{number}_{scen.label}"
    print(f"Sediment bulk density: {density:g} kg/m3")
    print(f"Scenario {number}: {scen.description}")
    watershed_dir = OUTPUT_DIR / f"{stem}_Watershed"
    watershed_dir.mkdir(parents=True, exist_ok=True)
    print(f"Portfolio: {csv_path}")

    dams = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"Dam_ID": str})[INPUT_COLS]
    dams = dams.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)
    dup = dams[dams["Dam_ID"].duplicated(keep=False)]
    if len(dup):
        raise SystemExit(f"Dam_ID must be unique — fix these rows in {csv_path.name}:\n"
                         f"{dup.to_string()}")
    print(f"  → {len(dams)} dams\n")

    # 1. Sub-basin of each dam, with its HydroATLAS attributes
    print("Loading BasinATLAS level-12 graph …")
    fid_of, children = hd.load_basin_graph()
    print(f"  → {len(fid_of):,} sub-basins\n")

    print("Locating dams in sub-basins …")
    attr_rows = []
    for dam in dams.itertuples():
        hit = hd.locate_subbasin(dam.Latitude, dam.Longitude)
        attr_rows.append(None if hit is None else hit.drop(columns="geometry").iloc[0])
    attr_cols = next(r.index for r in attr_rows if r is not None)
    attrs = pd.DataFrame([r if r is not None else pd.Series(index=attr_cols, dtype=float)
                          for r in attr_rows], columns=attr_cols).reset_index(drop=True)
    dams["HYBAS_ID"] = attrs["HYBAS_ID"].astype("Int64")
    unmatched = dams[dams["HYBAS_ID"].isna()]
    print(f"  → {len(dams) - len(unmatched)} matched, {len(unmatched)} outside any sub-basin")
    if len(unmatched):
        print(unmatched[["Dam_ID", "Dam_Name", "Latitude", "Longitude"]].to_string(index=False))
    print()

    # 2. Upstream dams, sub-basin counts
    upstream = hd.assign_upstream_dams(dams, children)
    dams["Upstream_Dams"] = [", ".join(upstream[d][0]) for d in dams["Dam_ID"]]
    dams["Nb_Sub_Basins"] = [len(hd.upstream_subbasins(int(h), children)) if pd.notna(h) else pd.NA
                             for h in dams["HYBAS_ID"]]

    # 3. Per-dam GeoPackages (only the missing ones)
    matched = dams[dams["HYBAS_ID"].notna()]
    todo = [d for d in matched["Dam_ID"] if not (watershed_dir / f"{d}.gpkg").exists()]
    print(f"GeoPackages: {len(matched) - len(todo)} already present, {len(todo)} to build")
    diagnostics = {}
    if todo:
        print("Loading HydroRIVERS network graph …")
        river_next_down, river_fid = hd.load_river_graph()
        dams_all = dams.set_index("Dam_ID", drop=False)
        for i, dam_id in enumerate(todo, 1):
            dam = dams_all.loc[dam_id]
            diag = hd.export_dam(dam, upstream[dam_id][0], dams_all, fid_of, children,
                                 river_next_down, river_fid, watershed_dir / f"{dam_id}.gpkg")
            diagnostics[dam_id] = diag
            print(f"  [{i}/{len(todo)}] {dam_id} ({dam['Dam_Name']}): {diag['n_sub_basins']} sub-basins, "
                  f"{diag['n_upstream_dams']} upstream dams, downstream {diag['downstream_status']}")
    print("Landslide hazard layer (watersheds that do not have it yet) …")
    n_hazard = LandslideHazard.ensure_layers(watershed_dir, matched["Dam_ID"])
    print(f"  → {n_hazard} added")
    hazard = LandslideHazard.shares(watershed_dir, matched["Dam_ID"])
    merged = hd.merge_gpkgs(watershed_dir)
    print(f"  → merged: {merged}\n")

    # River flag read from the GeoPackages themselves, so it is also right for reused files
    no_river = [d for d in matched["Dam_ID"]
                if "River_Downstream" not in pyogrio.list_layers(watershed_dir / f"{d}.gpkg")[:, 0]]
    # 4. Calculations and output CSV (column order of Template_Hydrosheds.csv)
    table = pd.concat([dams.drop(columns="HYBAS_ID"), attrs], axis=1)
    table["QC_flag_River"] = ["no_ok" if d in no_river or pd.isna(h) else "ok"
                              for d, h in zip(dams["Dam_ID"], dams["HYBAS_ID"])]
    for col in hazard.columns:                       # share of the watershed per landslide hazard class
        table[col] = table["Dam_ID"].map(hazard[col])
    table = calcs.compute_screening(table, density, scen.a, scen.b, scen.te)
    table = table[INPUT_COLS + calcs.CALC_COLUMNS + list(attr_cols)]
    out_csv = OUTPUT_DIR / f"{run_name}.csv"
    table.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"✓ {out_csv}  ({table.shape[0]} rows × {table.shape[1]} columns)")

    diag_rows = [{"Dam_ID": d, "HYBAS_ID": h,
                  "river_downstream": "NOT FOUND" if d in no_river else "found",
                  "same_subbasin_order_unknown": ", ".join(upstream[d][1]),
                  **{k: v for k, v in diagnostics.get(d, {}).items() if k not in ("Dam_ID", "HYBAS_ID")},
                  "scenario": number, "sdr_option": scen.sdr, "sdr_a": scen.a, "sdr_b": scen.b,
                  "te_option": scen.te, "density_kg_m3": density}
                 for d, h in zip(dams["Dam_ID"], dams["HYBAS_ID"])]
    pd.DataFrame(diag_rows).to_csv(OUTPUT_DIR / f"{run_name}_diagnostics.csv", index=False)

    # 5. Plots
    print("Plots:")
    ScreeningPlots.plot_run(table, run_name, scen.description, density)

    n_plot = len(ScreeningPlots.plottable(table))
    print(f"\n{n_plot} of {len(table)} dams passed the QC filters for plotting.")
    no_cap = table.loc[table["QC_flag_Capacity"] == "no_ok", "Dam_ID"].tolist()
    if no_cap:
        print(f"  {len(no_cap)} dam(s) have no reservoir capacity (QC_flag_Capacity = no_ok) "
              f"and are left out of the plots: {', '.join(no_cap)}")

    if no_river or len(unmatched):
        print("\n" + "!" * 78)
        if no_river:
            print(f"WARNING: no HydroRIVERS reach within {hd.SNAP_RADIUS_M:.0f} m for {len(no_river)} dam(s) — "
                  "River_Downstream NOT generated:")
            names = dict(zip(dams["Dam_ID"], dams["Dam_Name"]))
            for d in no_river:
                print(f"  {d}  {names[d]}")
        if len(unmatched):
            print(f"WARNING: {len(unmatched)} dam(s) fall outside every sub-basin and have no results: "
                  f"{', '.join(unmatched['Dam_ID'])}")
        print("Check the dam coordinates (see the *_Hydrosheds_diagnostics.csv, column river_downstream).")
        print("!" * 78)


if __name__ == "__main__":
    main()
