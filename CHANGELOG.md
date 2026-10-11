# Changelog

All notable changes to a project derived from this template should be
recorded here, following [Keep a Changelog](https://keepachangelog.com/)
conventions and [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Reservoir sedimentation screening tool (`Module/RunScreening.py`): per-dam
  HydroBASINS/HydroATLAS level-12 delineation, upstream dams, per-dam and
  merged GeoPackages, `<portfolio>_Hydrosheds.csv` with the 24 calculated
  columns and 296 HydroATLAS attributes, and lower-/higher-loss screening
  diagrams (`Module/HydroshedsDelineation.py`, `SedimentationCalcs.py`,
  `ScreeningPlots.py`; diagram data in `Resources/`).
- Dependencies: `matplotlib`, `pyogrio`.
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

## [0.1.0] - YYYY-MM-DD
### Added
- Initial version.
