# Run Commands

Quick reference for the standard commands in this project. All Python
commands are run through `uv run` so they use the project's managed
virtual environment.

## Setup (once, after cloning or copying this template)

```bash
uv sync
```
Creates `.venv` and installs everything listed in `pyproject.toml`.

## Running the screening

```bash
uv run python Module/RunScreening.py
```
Opens a file dialog (starting in `Data/`) to pick the portfolio CSV, asks for the
deposited-sediment bulk density (Enter = 1200 kg/m3), then
delineates every dam, writes `Output/<portfolio>_Hydrosheds.csv`, the
GeoPackages in `Output/<portfolio>_Watershed/` and the two diagrams in `Plot/`.

Without the dialog (the argument is a full path or a filename in `Data/`):
```bash
uv run python Module/RunScreening.py Template.csv --density 1200
```
Existing `<Dam_ID>.gpkg` files are reused; delete the `<portfolio>_Watershed`
folder to rebuild everything.

Re-draw only the diagrams from an existing output CSV:
```bash
uv run python Module/ScreeningPlots.py
```

## Managing dependencies

Add a package:
```bash
uv add <package>
```

Remove a package:
```bash
uv remove <package>
```

Re-sync the environment after manually editing `pyproject.toml`:
```bash
uv sync
```

## Versioning and releases

This project follows [SemVer](https://semver.org/) (`MAJOR.MINOR.PATCH`).
See the "Versioning" section in `README.md` for the full convention.

When a change is worth recording, add a bullet under `[Unreleased]` in
`CHANGELOG.md` -- no command needed, just edit the file.

When it's time to tag a release:
1. Update `version` in `pyproject.toml`.
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading.
3. Commit and tag:
   ```bash
   git commit -am "Bump version to X.Y.Z"
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin main --tags
   ```
   (confirm your default branch name first -- `git branch -vv` --
   rather than assuming `main`.)

## Memory (mnema)

See `CLAUDE.md` → "Memory (mnema)" for what each store is and when to use
it. Commands only, here.

One-time, per new project:
```bash
mnema --store ./Resources/.mnema init
mnema vault add ~/MyProjects/MyPython/.mnema-doctrine --name doctrine
./mount-library.sh   # mounts every library-<shard> vault (auto-discovered)
```

Day to day:
```bash
mnema --store ./Resources/.mnema ask "<question>"                # local + doctrine + all library shards
mnema --store ./Resources/.mnema ask --local "<question>"        # this project only
mnema --store ./Resources/.mnema remember "<decision and why>"
```

The library corpus is sharded into ~166 vaults (`library-ICOLD-1`, `library-WB-4`,
...) rather than one `library` vault -- a single store's capacity is ~D live
entries, and the corpus is far larger than any sane `--dim` can hold in one
store. There's no single name to `--except` anymore; to keep doctrine but skip
the whole corpus for one query:
```bash
mnema --store ./Resources/.mnema ask $(mnema vault list | awk '{print $1}' | grep '^library-' | sed 's/^/--except /') "<question>"
```

If it's slow (~10s per call), start the warm-model daemon once per machine:
```bash
mnema serve &
```
