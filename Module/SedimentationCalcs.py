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
AREA_TOLERANCE = 0.20           # QC_flag_Area: |pourpoint - catchment| / catchment
M3S_TO_HM3_YR = 31.536          # m3/s -> hm3/year

CALC_COLUMNS = [
    "Pourpoint_Area_km2", "QC_flag_Area", "Inflow_hm3", "QC_flag_Capacity", "C/I",
    "Upstream_Dams", "Storage_Upstream_hm3", "Degree_Regulation", "DoR_Cat",
    "Nb_Sub_Basins", "Erosion_hm3",
    "Low_SDR", "Low_TE", "Low_Sed_hm3", "Low_C/S", "QC_flag_Low",
    "High_SDR", "High_TE", "High_Sed_hm3", "High_C/S", "QC_flag_High",
    "Operation_Year", "Reservoir_Cat",
    "QC_flag_River",    # set by RunScreening from the per-dam GeoPackages
]


# ── Relationships (equations 4-7 of the note) ─────────────────────────────────

def sdr_lower(area_km2):
    """Diato & Grauso (2009), Italian catchments."""
    return 0.41 * area_km2 ** -0.085


def sdr_upper(area_km2):
    """Gourfi et al. (2018), Moroccan catchments."""
    return 0.93 * area_km2 ** -0.084


def te_lower(x):
    """Gill (1979) fit to the lower Brune curve (fine sediment); x = C/I."""
    return x**3 / (1.02655 * x**3 + 0.02621 * x**2 - 0.000133 * x + 0.000001)


def te_upper(x):
    """Gill (1979) fit to the upper Brune curve (coarse sediment); x = C/I.
    The published fit tends to 1.005 for large x, so it is capped at 1."""
    return np.minimum(x**2 / (0.994701 * x**2 + 0.006297 * x + 0.000003), 1.0)


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

def compute_screening(df, density_kg_m3=DEFAULT_DENSITY_KG_M3, year=None):
    """df needs: Dam_ID, Construction_Year, Reservoir_hm3, Catchment_km2,
    Upstream_Dams (", "-separated Dam_IDs or empty), Nb_Sub_Basins, and the
    HydroATLAS columns UP_AREA, dis_m3_pyr and ero_kh_uav. density_kg_m3 is the
    bulk density of the deposited sediment, used to convert eroded mass to volume."""
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
    df["DoR_Cat"] = pd.cut(df["Degree_Regulation"], bins=[-np.inf, 0.2, 0.5, np.inf],
                           labels=[1, 2, 3], right=False).astype("Int64")
    # right=False puts exactly 0.5 in cat 3; the note says "between 0.2 and 0.5" is 2
    df.loc[df["Degree_Regulation"] == 0.5, "DoR_Cat"] = 2

    # ero_kh_uav [kg/ha/yr] x 100 [ha/km2] x UP_AREA [km2] / density [kg/m3] -> m3/yr -> hm3/yr
    df["Erosion_hm3"] = df["ero_kh_uav"] * 100 * area / density_kg_m3 / 1e6

    for tag, sdr, te in (("Low", sdr_lower, te_lower), ("High", sdr_upper, te_upper)):
        df[f"{tag}_SDR"] = sdr(area)
        df[f"{tag}_TE"] = te(x)
        df[f"{tag}_Sed_hm3"] = df["Erosion_hm3"] * df[f"{tag}_SDR"] * df[f"{tag}_TE"]
        df[f"{tag}_C/S"] = cap / df[f"{tag}_Sed_hm3"].where(df[f"{tag}_Sed_hm3"] > 0)
        df[f"QC_flag_{tag}"] = _flag_cs(df[f"{tag}_C/S"])

    df["Operation_Year"] = (year - cons_year).astype("Int64").astype("object").where(
        cons_year.notna(), "N/A")
    df["Reservoir_Cat"] = _reservoir_cat(cap)
    return df
