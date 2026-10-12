# Changelog

All notable changes to a project derived from this template should be
recorded here, following [Keep a Changelog](https://keepachangelog.com/)
conventions and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-12
### Added
- `Landslide_hazard` layer in every dam GeoPackage (`Module/LandslideHazard.py`): the global landslide hazard map
  (ThinkHazard!, levels very low to high) clipped to the watershed, one polygon per class with area and share;
  also in `All_Dams.gpkg`. Existing GeoPackages get the layer without being delineated again. Dependency: `rasterio`.
- Four output columns with the share of the watershed in each landslide hazard class (`Landslide_VeryLow_pct`,
  `Landslide_Low_pct`, `Landslide_Medium_pct`, `Landslide_High_pct`, after `QC_flag_River`): 326 columns.
- Sediment scenario chosen per run (`Module/Scenario.py`): SDR low (Diodato), high (Gourfi) or user-defined
  `a x A^b`, and TE low (Gill lower curve), medium (Brune median, `(C/I)/(0.012 + 1.02 C/I)`) or high (Gill upper
  curve); terminal menus or `--sdr/--a/--b/--te`. Files are named
  `<portfolio>_Hydrosheds_Scen<#>_SDR_<..>_TE_<..>` (`<#>` = next free number, `--scen-number`).
### Changed
- **Output format change.** The Low_* and High_* column blocks are replaced by one block for the chosen scenario
  (`SDR`, `TE`, `Sed_hm3`, `C/S`, `QC_flag_CS`), and one diagram is drawn per run instead of two. Output files are now
  named `..._Scen<#>_SDR_<..>_TE_<..>`. The output has 322 columns, 326 with the hazard columns. Low/Low and
  High/High reproduce the 0.1.0 lower- and higher-loss results exactly. The scenario parameters are recorded in the
  diagnostics file.

## [0.1.0] - 2026-10-12
### Added
- Reservoir sedimentation screening tool (`Module/RunScreening.py`): per-dam
  HydroBASINS/HydroATLAS level-12 delineation, upstream dams, per-dam and
  merged GeoPackages, `<portfolio>_Hydrosheds.csv` with the 24 calculated
  columns and 296 HydroATLAS attributes, and lower-/higher-loss screening
  diagrams (`Module/HydroshedsDelineation.py`, `SedimentationCalcs.py`,
  `ScreeningPlots.py`; diagram data in `Resources/`).
- Dependencies: `matplotlib`, `pyogrio`.
- `DoR_Cat = 4` when at least one upstream dam has no storage information (magenta in the diagrams,
  legend "Upstream storage unknown").
- Sediment bulk density is a run parameter (default 1200 kg/m3; prompt or `--density`).
- Screening diagrams: Arial font, red dashed 300-year line, left-aligned technique box, and
  enlarged labels.
- `QC_flag_River` column (ok / no_ok) in the output CSV, after `Reservoir_Cat`.
- End-of-run warning (and `river_downstream` column in the diagnostics CSV) for dams with
  no HydroRIVERS reach within the snap radius; dams without capacity are listed and left
  out of the plots; duplicate `Dam_ID`s stop the run.
- mnema memory scaffolding: per-project store at `Resources/.mnema`, plus
  `doctrine` and `library` read-only vaults. See `CLAUDE.md` → "Memory
  (mnema)" and `RUN_COMMANDS.md` → "Memory (mnema)".
