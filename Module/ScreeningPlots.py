"""
ScreeningPlots.py
=================
Step iii: reservoir sedimentation screening diagram (Figure 1 of the
methodological note), one per scenario (lower-loss / higher-loss).

  - x = C/I, y = C/S (log-log), S-curve and technique regions 1-3 from
    Resources/S_curve.csv and Resources/Technique_areas.csv
  - dot size = reservoir capacity class (5 classes, small to large)
  - dot colour = DoR_Cat (green 1, orange 2, red 3, magenta 4 = an upstream dam has no storage data)
  - only dams with QC_flag_Area in (ok, N/A) and QC_flag_Capacity = ok

Imported by RunScreening.py. Can also be run alone on an existing output CSV:
    uv run python Module/ScreeningPlots.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

plt.rcParams["font.family"] = "Arial"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = PROJECT_ROOT / "Resources"
OUTPUT_DIR = PROJECT_ROOT / "Output"
PLOT_DIR = PROJECT_ROOT / "Plot"

CAPACITY_CLASSES = ["<3 hm3", "3-10 hm3", "10-50 hm3", "50-100 hm3", ">100 hm3"]
MARKER_AREAS = [8, 25, 55, 100, 170]                 # points^2, small to large
DOR_COLORS = {1: "tab:green", 2: "orange", 3: "tab:red", 4: "magenta"}
DOR_LABELS = {1: "DoR < 0.2", 2: "0.2 ≤ DoR ≤ 0.5", 3: "DoR > 0.5",
              4: "Upstream storage unknown"}
SCENARIOS = {"Low": "Lower-loss scenario", "High": "Higher-loss scenario"}

CS_THRESHOLD_YEARS = 300                              # screening threshold, Annandale (2013)
XLIM, YLIM = (1e-4, 10), (0.1, 1e4)
REGION_LABEL_POS = {1: (1.3e-4, 3.6), 2: (1.3e-3, 14), 3: (4, 450)}   # circled numbers


def plottable(df):
    """Rows allowed on the diagram, per the note (section 3.4, action 1e)."""
    return df[df["QC_flag_Area"].isin(["ok", "N/A"]) & (df["QC_flag_Capacity"] == "ok")]


def plot_scenario(df, scenario, out_path, density=None):
    """Draw one diagram and return the number of plotted dams outside the axes."""
    d = plottable(df)
    x, y = d["C/I"], d[f"{scenario}_C/S"]
    d = d[x.notna() & y.notna()]
    x, y = d["C/I"], d[f"{scenario}_C/S"]
    outside = int(((x < XLIM[0]) | (x > XLIM[1]) | (y < YLIM[0]) | (y > YLIM[1])).sum())

    fig, ax = plt.subplots(figsize=(11, 7.5))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(XLIM); ax.set_ylim(YLIM)
    ax.grid(True, which="major", color="0.85", lw=0.7)
    ax.set_axisbelow(True)

    # Diagram background: S-curve and technique regions
    s_curve = pd.read_csv(RESOURCES_DIR / "S_curve.csv")
    ax.plot(s_curve["C/I"], s_curve["C/S"], color="red", lw=1.8, zorder=2)
    ax.axhline(CS_THRESHOLD_YEARS, color="red", ls="--", lw=1.2, zorder=1.9)
    ax.text(1.2e-4, CS_THRESHOLD_YEARS * 1.08, f"{CS_THRESHOLD_YEARS} years", color="red",
            ha="left", va="bottom", fontsize=11, zorder=5)
    areas = pd.read_csv(RESOURCES_DIR / "Technique_areas.csv")
    for n, poly in areas.groupby("Area"):
        ax.plot(poly["C/I"], poly["C/S"], color="black", ls="--", lw=1.4, zorder=2)
        ax.annotate(str(n), REGION_LABEL_POS[n], ha="center", va="center", fontsize=9, zorder=5,
                    bbox=dict(boxstyle="circle,pad=0.3", fc="white", ec="black"))
    ax.text(5e-4, 3.6, "Potentially sustainable", color="green", ha="center", va="center",
            fontsize=10, fontweight="bold", bbox=dict(fc="white", ec="green"))
    ax.text(0.4, 1.5, "Non-sustainable", color="red", ha="center", va="center",
            fontsize=10, fontweight="bold", bbox=dict(fc="white", ec="red"))
    ax.text(0.0016, 0.14, "1. Flushing, sluicing, hydrosuction, and/or dredging\n"
            "2. Flushing, sluicing, excavation, dredging, bypassing, and/or check dams\n"
            "3. Storage operation, and/or density current venting\n\n"
            "source: modified from Annandale, 2013",
            fontsize=9, va="bottom", ha="left", multialignment="left",
            bbox=dict(fc="white", ec="black"))

    # Dams: size = capacity class, colour = degree of regulation
    for cls, area in zip(CAPACITY_CLASSES, MARKER_AREAS):
        for cat, color in DOR_COLORS.items():
            s = d[(d["Reservoir_Cat"] == cls) & (d["DoR_Cat"] == cat)]
            ax.scatter(s["C/I"], s[f"{scenario}_C/S"], s=area, c=color, alpha=0.75,
                       edgecolor="k", linewidth=0.3, zorder=3)

    size_handles = [Line2D([], [], marker="o", ls="", mfc="0.6", mec="k", mew=0.3,
                           ms=np.sqrt(a), label=c) for c, a in zip(CAPACITY_CLASSES, MARKER_AREAS)]
    color_handles = [Line2D([], [], marker="o", ls="", mfc=DOR_COLORS[k], mec="k", mew=0.3,
                            ms=7, label=DOR_LABELS[k]) for k in DOR_COLORS]
    leg1 = ax.legend(handles=size_handles, title="Reservoir capacity", loc="lower right",
                     fontsize=8, title_fontsize=8, framealpha=0.95, bbox_to_anchor=(1, 0.2))
    ax.add_artist(leg1)
    ax.legend(handles=color_handles, title="Degree of regulation", loc="lower right",
              fontsize=8, title_fontsize=8, framealpha=0.95, bbox_to_anchor=(1, 0))

    ax.set_xlabel("Reservoir Capacity / Mean Annual Runoff  (C/I)")
    ax.set_ylabel("Reservoir Capacity / Mean Annual Storage Loss  (C/S)")
    ax.set_title(f"Applicability of sediment management techniques – {SCENARIOS[scenario]}",
                 fontweight="bold", color="0.35")
    note = f"{len(d)} dams plotted of {len(df)} in the portfolio"
    if outside:
        note += f"; {outside} outside the axes"
    if density is not None:
        note += f"; sediment bulk density {density:g} kg/m3"
    fig.text(0.01, 0.005, note, fontsize=7, color="0.4")

    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return outside


def plot_all(df, stem, density=None):
    """Write Plot/<stem>_<Low|High>.png for both scenarios."""
    for scenario in SCENARIOS:
        path = PLOT_DIR / f"{stem}_{scenario}.png"
        outside = plot_scenario(df, scenario, path, density)
        print(f"  → {path.name}" + (f" ({outside} dams outside the axes)" if outside else ""))


if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    chosen = filedialog.askopenfilename(title="Select a *_Hydrosheds.csv output file",
                                        initialdir=OUTPUT_DIR, filetypes=[("CSV files", "*.csv")])
    root.destroy()
    if not chosen:
        raise SystemExit("No file selected — exiting.")
    table = pd.read_csv(chosen, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    plot_all(table, Path(chosen).stem.removesuffix("_Hydrosheds"))
