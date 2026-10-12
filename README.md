# Reservoir Sedimentation Screening (HydroSHEDS)

Portfolio-level screening of reservoir sedimentation risk for existing dams,
built on HydroSHEDS data (HydroBASINS / HydroATLAS level 12, HydroRIVERS).
For each dam it delineates the upstream catchment, estimates annual storage loss
under a sediment scenario chosen by the user (delivery ratio and trapping efficiency), and places every
reservoir on the Annandale sediment-management screening diagram (C/I vs C/S).

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
2. **Calculations** — the 23 derived columns (inflow, C/I, degree of
   regulation, erosion, SDR, trapping efficiency, sediment volume, C/S, QC
   flags…) plus the 296 HydroATLAS attributes of the dam's sub-basin.
3. **Plots** — the screening diagram of the chosen scenario.

## Outputs

| File | Content |
|---|---|
| `Output/<portfolio>_Hydrosheds_Scen<#>_SDR_<..>_TE_<..>.csv` | input + 23 calculated columns (incl. the 4 landslide hazard shares) + 296 HydroATLAS columns (326 in total) |
| `Output/<same name>_diagnostics.csv` | per dam: sub-basin, snap distance, downstream status, same-sub-basin dams whose order is unknown, and the scenario parameters |
| `Output/<portfolio>_Watershed/<Dam_ID>.gpkg` | layers `Dams`, `Watershed`, `Sub_basins`, `River_Networks`, `River_Downstream`, `Landslide_hazard` |
| `Output/<portfolio>_Watershed/All_Dams.gpkg` | the same 6 layers merged, one feature per dam / sub-basin / river reach (hazard: per dam and class) |
| `Plot/<same name>.png` | screening diagram of the scenario |

## Sediment scenario

Each run uses one sediment delivery ratio (SDR) and one trapping efficiency (TE), chosen in the terminal
(or with `--sdr`, `--a`, `--b`, `--te`):

| | Low | Medium | High |
|---|---|---|---|
| SDR | Diodato & Grauso (2009): `0.41 × A^-0.085` | – | Gourfi et al. (2018): `0.93 × A^-0.084` |
| TE (`x` = C/I) | Gill (1979) fit to the lower Brune curve, fine sediment | Brune median curve: `x / (0.012 + 1.02 x)` | Gill (1979) fit to the upper Brune curve, coarse sediment (capped at 1) |

A third SDR option is user-defined, `SDR = a × A^b` with `A` in km² and `a` (> 0) and `b` typed by the user
(`--sdr user --a 0.5 --b -0.1`); the SDR is not capped at 1. The sediment volume is
`S = Erosion_hm3 × SDR × TE` and `C/S = Reservoir_hm3 / S`.

The output files are named `..._Scen<#>_SDR_<Low|High|User>_TE_<Low|Medium|High>`, where `<#>` is the next free
scenario number of the portfolio (`--scen-number N` sets it). The `a` and `b` of a user-defined SDR are not in
the name: they are in the diagnostics file (columns `sdr_a`, `sdr_b`) and in the subtitle of the diagram.
Low/Low and High/High reproduce the earlier lower-loss and higher-loss results exactly.

## Modules

| Script | Role |
|---|---|
| `Module/RunScreening.py` | entry point: file picker, orchestration, CSV output |
| `Module/HydroshedsDelineation.py` | delineation, upstream dams, GeoPackage export and merge |
| `Module/Scenario.py` | the sediment scenario: menus, `--sdr/--a/--b/--te`, file naming |
| `Module/SedimentationCalcs.py` | all formulas of the note (equations 1–7) |
| `Module/LandslideHazard.py` | the `Landslide_hazard` layer: hazard map clipped to each watershed |
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
- Upstream dams with no `Reservoir_hm3` add nothing to `Storage_Upstream_hm3`, so the degree of
  regulation is only a lower bound: such a dam gets `DoR_Cat = 4` (magenta, "Upstream storage unknown")
  instead of 1–3. A dam with no upstream dams has `Degree_Regulation = 0` and `DoR_Cat = 1`.
- The upper Gill/Brune trapping-efficiency fit exceeds 1 for large C/I; it is capped at 1.
- QC flags use the text values `ok`, `no_ok` and `N/A`. `QC_flag_CS` is 0 when C/S ≥ 300 years, else 1.
- `River_Networks` keeps the reaches whose representative point lies inside the watershed.
- Merged layers keep one feature per `Dam_ID` / `HYBAS_ID` / `HYRIV_ID`, since
  nested watersheds share sub-basins and reaches.
- Dams with no `Reservoir_hm3` get `QC_flag_Capacity = no_ok`, have no C/I or C/S and are left out of the
  plots; they stay in the CSV.
- **Landslide hazard.** Every dam GeoPackage has a `Landslide_hazard` layer: the global landslide hazard map
  (qualitative ThinkHazard! levels 1–4 = very low, low, medium, high; about 1 km; 60° S to 72° N) clipped to the
  watershed outline. It holds one polygon per hazard class present, with `Dam_ID`, `Hazard_Level`, `Hazard_Class`,
  `Area_km2` and `Share_pct` (share of the watershed area). Lakes, oceans and areas outside the map are not drawn,
  so the shares can add up to less than 100 %, and a watershed outside the map has no layer. The merged file keeps
  one polygon per dam and class (hazard areas differ between nested watersheds). The map serves regional-scale
  decisions, not site-specific assessment. The four shares are also in the output CSV (`Landslide_VeryLow_pct`, `Landslide_Low_pct`, `Landslide_Medium_pct`,
  `Landslide_High_pct`, after `QC_flag_River`); they are blank for dams without a layer.
- Dams with no HydroRIVERS reach within 2 km get no `River_Downstream` layer and `QC_flag_River = no_ok`
  (`ok` otherwise). They are listed in a warning
  at the end of the run and marked `NOT FOUND` in the diagnostics file (column `river_downstream`).
- Plot axes are fixed as in the note; dams beyond them are counted in the figure footnote.

## Run

```bash
uv run python Module/RunScreening.py [portfolio.csv] [--sdr low|high|user [--a A --b B]] [--te low|medium|high] [--density 1200]
```

## References

- Ove Arup & Partners International Ltd. 2020. The Global Landslide Hazard Map. Final Project Report, prepared for
  GFDRR and The World Bank, 26 June 2020.

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

[SemVer](https://semver.org/) (`MAJOR.MINOR.PATCH`), with notable changes in `CHANGELOG.md`. While the major
version is 0, a MINOR release adds features or changes the output format (columns, file names), and a PATCH release
only fixes bugs; 1.0.0 will mean the output format is stable. Each release is a commit that sets `version` in
`pyproject.toml` and the dated section of the changelog, tagged `vX.Y.Z`; the tags are on GitHub.
