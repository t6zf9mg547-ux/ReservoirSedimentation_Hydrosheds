"""
SedimentationCalcs.py
=====================
Steps ii (HydroATLAS-derived columns) and the sediment delivery / trapping
calculations of the screening methodology (methodological note, sections 3.1
and 3.4). Pure pandas/numpy: takes the portfolio table already joined with
the HydroATLAS attributes and the Upstream_Dams column, and returns it with
the 24 calculated columns filled in.

Imported by RunScreening.py.
"""

from datetime import date

import numpy as np
import pandas as pd

DEFAULT_DENSITY_KG_M3 = 1200.0  # deposited-sediment bulk density (default)
CS_THRESHOLD_YEARS = 300.0      # Annandale (2013) screening threshold
DOR_FLAG_RELATIVE = 0.20         # QC_flag_DOR: relative difference between the two degrees of regulation ...
DOR_FLAG_ABSOLUTE = 0.05         # ... and absolute difference above which they are inconsistent
AREA_TOLERANCE = 0.20           # QC_flag_Area: |pourpoint - catchment| / catchment
M3S_TO_HM3_YR = 31.536          # m3/s -> hm3/year

CALC_COLUMNS = [
    "Pourpoint_Area_km2", "QC_flag_Area", "Inflow_hm3", "QC_flag_Capacity", "C/I",
    "Upstream_Dams", "Storage_Upstream_hm3", "Degree_Regulation", "Degree_Regulation_HA", "DoR_Cat", "QC_flag_DOR",
    "Nb_Sub_Basins", "Erosion_hm3",
    "SDR", "TE", "Sed_hm3", "C/S", "QC_flag_CS",     # the chosen sediment scenario (see Scenario.py)
    "Operation_Year", "Reservoir_Cat",
    "QC_flag_River",    # set by RunScreening from the per-dam GeoPackages
    "Landslide_VeryLow_pct", "Landslide_Low_pct", "Landslide_Medium_pct", "Landslide_High_pct",   # LandslideHazard.shares
]


# ── Relationships ─────────────────────────────────────────────────────────────

def sdr(area_km2, a, b):
    """Sediment delivery ratio a x A^b, A in km2 (presets in Scenario.SDR_OPTIONS: Diodato &
    Grauso 2009 with 0.41 and -0.085, Gourfi et al. 2018 with 0.93 and -0.084). Not capped."""
    return a * area_km2 ** b


def te_low(x):
    """Gill (1979) fit to the lower Brune curve (fine sediment); x = C/I."""
    return x**3 / (1.02655 * x**3 + 0.02621 * x**2 - 0.000133 * x + 0.000001)


def te_medium(x):
    """Brune median curve; x = C/I."""
    return x / (0.012 + 1.02 * x)


def te_high(x):
    """Gill (1979) fit to the upper Brune curve (coarse sediment); x = C/I.
    The published fit tends to 1.005 for large x, so it is capped at 1."""
    return np.minimum(x**2 / (0.994701 * x**2 + 0.006297 * x + 0.000003), 1.0)


TE_FUNCTIONS = {"Low": te_low, "Medium": te_medium, "High": te_high}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flag_cs(cs):
    """QC_flag: 0 if C/S >= 300 years, 1 otherwise, blank if C/S is unavailable."""
    return pd.Series(np.where(cs.isna(), pd.NA, (cs < CS_THRESHOLD_YEARS).astype(int)),
                     index=cs.index, dtype="Int64")


def _reservoir_cat(capacity):
    labels = ["<3 hm3", "3-10 hm3", "10-50 hm3", "50-100 hm3", ">100 hm3"]
    cat = pd.cut(capacity, bins=[-np.inf, 3, 10, 50, 100, np.inf], labels=labels, right=False)
    return cat.astype("object").where(capacity.notna(), None)


# ── Main ──────────────────────────────────────────────────────────────────────

def compute_screening(df, density_kg_m3, sdr_a, sdr_b, te_option, year=None):
    """df needs: Dam_ID, Construction_Year, Reservoir_hm3, Catchment_km2,
    Upstream_Dams (", "-separated Dam_IDs or empty), Nb_Sub_Basins, and the
    HydroATLAS columns UP_AREA, dis_m3_pyr and ero_kh_uav. density_kg_m3 is the
    bulk density of the deposited sediment, used to convert eroded mass to volume.
    The sediment scenario is SDR = sdr_a x A^sdr_b and the trapping efficiency curve te_option
    ("Low", "Medium" or "High")."""
    year = year or date.today().year
    df = df.copy()
    cap = pd.to_numeric(df["Reservoir_hm3"], errors="coerce")
    catch = pd.to_numeric(df["Catchment_km2"], errors="coerce")
    cons_year = pd.to_numeric(df["Construction_Year"], errors="coerce")

    area = df["UP_AREA"]
    df["Pourpoint_Area_km2"] = area
    rel_diff = (area - catch).abs() / catch
    df["QC_flag_Area"] = np.where(catch.isna(), "N/A",
                                  np.where(rel_diff < AREA_TOLERANCE, "ok", "no_ok"))

    df["Inflow_hm3"] = df["dis_m3_pyr"] * M3S_TO_HM3_YR
    df["QC_flag_Capacity"] = np.where(cap.notna() & (cap > 0), "ok", "no_ok")
    inflow = df["Inflow_hm3"].where(df["Inflow_hm3"] > 0)
    x = cap / inflow
    df["C/I"] = x

    # Upstream storage: capacities of the listed upstream dams (missing ones count as 0)
    cap_of = dict(zip(df["Dam_ID"], cap))
    ups = df["Upstream_Dams"].fillna("")
    df["Storage_Upstream_hm3"] = [
        sum(np.nan_to_num(cap_of.get(d, 0.0)) for d in s.split(", ") if d) for s in ups]
    df["Degree_Regulation"] = df["Storage_Upstream_hm3"] / inflow
    # HydroATLAS degree of regulation at the pour point (dor_pc_pva, stored as percent x 10): the storage
    # of all dams on or upstream of the reach over the annual discharge of that reach. Its own volume is
    # rebuilt with HydroATLAS's discharge, the dam's capacity (included in it) is deducted, and the result
    # is divided by this tool's inflow. Floored at 0; a dam without capacity deducts nothing.
    dor_volume = df["dor_pc_pva"] / 1000 * df["dis_m3_pyr"] * M3S_TO_HM3_YR
    df["Degree_Regulation_HA"] = (dor_volume - cap.fillna(0)).clip(lower=0) / inflow
    # DoR_Cat uses the larger of our value (identified upstream dams) and the HydroATLAS one
    regulation = np.fmax(df["Degree_Regulation"], df["Degree_Regulation_HA"])
    df["DoR_Cat"] = pd.cut(regulation, bins=[-np.inf, 0.2, 0.5, np.inf],
                           labels=[1, 2, 3], right=False).astype("Int64")
    # right=False puts exactly 0.5 in cat 3; "between 0.2 and 0.5" is 2
    df.loc[regulation == 0.5, "DoR_Cat"] = 2
    # Category 4: at least one upstream dam has no storage information, so the storage above
    # (and the degree of regulation) is only a lower bound and cannot be classified.
    unknown_storage = [any(not (cap_of.get(d, np.nan) > 0) for d in s.split(", ") if d) for s in ups]
    df.loc[unknown_storage, "DoR_Cat"] = 4
    # QC_flag_DOR: our value and the HydroATLAS one disagree by 20 % of the larger one or more, and by at
    # least 0.05 (so that tiny values do not trigger it); N/A when one of them is missing
    a, b = df["Degree_Regulation"], df["Degree_Regulation_HA"]
    diff, top = (a - b).abs(), np.fmax(a, b)
    inconsistent = (diff / top.where(top > 0) >= DOR_FLAG_RELATIVE) & (diff >= DOR_FLAG_ABSOLUTE)
    df["QC_flag_DOR"] = np.where(a.isna() | b.isna(), "N/A", np.where(inconsistent, "no_ok", "ok"))

    # ero_kh_uav [kg/ha/yr] x 100 [ha/km2] x UP_AREA [km2] / density [kg/m3] -> m3/yr -> hm3/yr
    df["Erosion_hm3"] = df["ero_kh_uav"] * 100 * area / density_kg_m3 / 1e6

    df["SDR"] = sdr(area, sdr_a, sdr_b)
    df["TE"] = TE_FUNCTIONS[te_option](x)
    df["Sed_hm3"] = df["Erosion_hm3"] * df["SDR"] * df["TE"]
    df["C/S"] = cap / df["Sed_hm3"].where(df["Sed_hm3"] > 0)
    df["QC_flag_CS"] = _flag_cs(df["C/S"])

    df["Operation_Year"] = (year - cons_year).astype("Int64").astype("object").where(
        cons_year.notna(), "N/A")
    df["Reservoir_Cat"] = _reservoir_cat(cap)
    return df
