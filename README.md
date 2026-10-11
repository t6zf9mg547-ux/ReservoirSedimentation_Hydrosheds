# Reservoir Sedimentation Screening (HydroSHEDS)

Portfolio-level screening of reservoir sedimentation risk for existing dams,
built on HydroSHEDS data (HydroBASINS / HydroATLAS level 12, HydroRIVERS).
For each dam it delineates the upstream catchment, estimates annual storage loss
under a lower-loss and a higher-loss scenario, and places every reservoir on the Annandale
sediment-management screening diagram (C/I vs C/S).

Results are for **screening and prioritisation only** — not a substitute for
site-specific sediment studies.

## Inputs

`Data/<portfolio>.csv` with 7 columns (see `Data/Template.csv`):

`Dam_ID, Dam_Name, Latitude, Longitude, Construction_Year, Reservoir_hm3, Catchment_km2`

`Dam_ID` must be unique. `Construction_Year`, and `Catchment_km2` may be empty.

HydroSHEDS data are read from `/Users/filou/MyProjects/MyGISProjects/Resources/Maps and data`
(`BasinATLAS/BasinATLAS_v10.gdb`, `HydroRIVERS/HydroRIVERS_v10_shp`); the paths
are constants at the top of `Module/HydroshedsDelineation.py`.

## What it does

1. **Delineation** — dam → level-12 sub-basin (point in polygon) → all upstream
   sub-basins (`NEXT_DOWN`) → watershed, river network, downstream river
   (dam snapped to the nearest HydroRIVERS reach within 2 km, then followed to
   the outlet), upstream portfolio dams.
2. **Calculations** — the 24 derived columns (inflow, C/I, degree of
   regulation, erosion, SDR, trapping efficiency, sediment volume, C/S, QC
   flags…) plus the 296 HydroATLAS attributes of the dam's sub-basin.
3. **Plots** — one screening diagram per scenario.

## Outputs

| File | Content |
|---|---|
| `Output/<portfolio>_Hydrosheds.csv` | input + calculated + 296 HydroATLAS columns (layout of `Output/Template_Hydrosheds.csv`, plus one extra column, `QC_flag_River`, after `Reservoir_Cat`) |
| `Output/<portfolio>_Hydrosheds_diagnostics.csv` | per dam: sub-basin, snap distance, downstream status, same-sub-basin dams whose order is unknown |
| `Output/<portfolio>_Watershed/<Dam_ID>.gpkg` | layers `Dams`, `Watershed`, `Sub_basins`, `River_Networks`, `River_Downstream` |
| `Output/<portfolio>_Watershed/All_Dams.gpkg` | the same 5 layers merged, one feature per dam / sub-basin / river reach |
| `Plot/<portfolio>_Low.png`, `_High.png` | screening diagrams, lower- and higher-loss scenario |

## Modules

| Script | Role |
|---|---|
| `Module/RunScreening.py` | entry point: file picker, orchestration, CSV output |
| `Module/HydroshedsDelineation.py` | delineation, upstream dams, GeoPackage export and merge |
| `Module/SedimentationCalcs.py` | all formulas of the note (equations 1–7) |
| `Module/ScreeningPlots.py` | screening diagram (also runnable alone on an output CSV) |
| `Resources/S_curve.csv`, `Resources/Technique_areas.csv` | curve and region coordinates of the diagram |

## Method notes and assumptions

- `A` in the SDR equations is `Pourpoint_Area_km2` (HydroATLAS `UP_AREA`).
- `Erosion_hm3 = ero_kh_uav [kg/ha/yr] × 100 × UP_AREA [km²] / density [kg/m³] / 10⁶`. The deposited-sediment
  bulk density is a run parameter (default 1200 kg/m³): asked at start-up, or passed as `--density`. It is
  printed in the diagram footnote.
- HydroATLAS values are those of the sub-basin pour point, not re-weighted to the
  dam position; `QC_flag_Area` shows where the two areas disagree by more than 20 %.
- Two dams in the same sub-basin are ordered by `Catchment_km2` (smaller =
  upstream). If either area is missing, or they differ by < 5 %, the order is
  unknown and neither is counted as upstream of the other (listed in the
  diagnostics file).
- Upstream dams with no `Reservoir_hm3` add nothing to `Storage_Upstream_hm3`.
  A dam with no upstream dams has `Degree_Regulation = 0` and `DoR_Cat = 1`.
- The upper Gill/Brune trapping-efficiency fit exceeds 1 for large C/I; it is capped at 1.
- QC flags use the text values `ok`, `no_ok` and `N/A`. `QC_flag_Low/High` is 0 when C/S ≥ 300 years, else 1.
- `River_Networks` keeps the reaches whose representative point lies inside the watershed.
- Merged layers keep one feature per `Dam_ID` / `HYBAS_ID` / `HYRIV_ID`, since
  nested watersheds share sub-basins and reaches.
- Dams with no `Reservoir_hm3` get `QC_flag_Capacity = no_ok`, have no C/I or C/S and are left out of the
  plots; they stay in the CSV.
- Dams with no HydroRIVERS reach within 2 km get no `River_Downstream` layer and `QC_flag_River = no_ok`
  (`ok` otherwise). They are listed in a warning
  at the end of the run and marked `NOT FOUND` in the diagnostics file (column `river_downstream`).
- Plot axes are fixed as in the note; dams beyond them are counted in the figure footnote.

## Run

```bash
uv run python Module/RunScreening.py [portfolio.csv] [--density 1200]
```

## Setup

```bash
uv sync
```
GDAL must be installed at system level (`brew install gdal`); `tkinter` is stdlib.
See `RUN_COMMANDS.md` for the command reference.

## Memory

Project decisions live in a [mnema](https://github.com/front-depiction/mnema)
store at `Resources/.mnema`. See `CLAUDE.md` → "Memory (mnema)" and
`RUN_COMMANDS.md`.

## Versioning

[SemVer](https://semver.org/); notable changes in `CHANGELOG.md`.
