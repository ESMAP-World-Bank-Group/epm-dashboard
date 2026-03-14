"""
Central data loader for the EPM Dashboard.
All CSV files are loaded here with lru_cache for performance.
Heavy files (dispatch, hourly price) are loaded on demand without caching.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache

DATA_ROOT = Path(__file__).parent.parent / "model_data"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COUNTRY_ISO = {
    "Burundi": "BDI", "DRC": "COD", "Djibouti": "DJI", "Egypt": "EGY",
    "Ethiopia": "ETH", "Kenya": "KEN", "Rwanda": "RWA", "Sudan": "SDN",
    "Tanzania": "TZA", "Uganda": "UGA", "Eritrea": "ERI", "Somalia": "SOM",
    "South Sudan": "SSD",
}

# Stacking order for technology types (bottom → top)
TECH_ORDER = [
    "Import", "Nuclear", "Coal", "Peat", "Diesel", "Gas", "CCGT", "OCGT",
    "Methane", "Waste", "Biomass", "Geothermal", "Reservoir", "ROR",
    "CSP", "Solar Thermal", "Solar", "Onshore Wind", "Offshore Wind",
    "PV", "PV+Storage", "Battery", "PSH",
]

TECH_COLORS = {
    "Reservoir":       "#1a6faf",
    "ROR":             "#5fa8d3",
    "PV":              "#f4c430",
    "PV+Storage":      "#e8971a",
    "Onshore Wind":    "#2d9e4f",
    "Offshore Wind":   "#7ec8a0",
    "Battery":         "#7b4f9e",
    "PSH":             "#b09bc8",
    "Solar Thermal":   "#f97b22",
    "Solar":           "#f4c430",
    "CSP":             "#f4a261",
    "Gas":             "#f77f00",
    "CCGT":            "#f77f00",
    "OCGT":            "#fcb777",
    "Coal":            "#5c4033",
    "Nuclear":         "#c1440e",
    "Biomass":         "#7a9e3b",
    "Waste":           "#9e8e6e",
    "Peat":            "#8b7355",
    "Methane":         "#d4a017",
    "Diesel":          "#d62728",
    "Import":          "#95afc0",
    "Imports":         "#95afc0",
    "Geothermal":      "#16a085",
    "Generation":      "#2c6fad",
    "StorageEnergy":   "#7b4f9e",
    # Cost categories
    "Fuel costs: $m":                             "#d62728",
    "Fixed O&M: $m":                              "#1a6faf",
    "Variable O&M: $m":                           "#5fa8d3",
    "Import costs with internal zones: $m":       "#95afc0",
    "Import costs with external zones: $m":       "#7f7f7f",
    "Export revenues with internal zones: $m":    "#2d9e4f",
    "Export revenues with external zones: $m":    "#7ec8a0",
    "Trade shared benefits: $m":                  "#27ae60",
    "Unmet demand costs: $m":                     "#e74c3c",
    "Unmet country planning reserve costs: $m":   "#fcb777",
    "Unmet country spinning reserve costs: $m":   "#f77f00",
    "Carbon costs: $m":                           "#c1440e",
    "Spinning reserve costs: $m":                 "#b09bc8",
    "Transmission costs: $m":                     "#7a9e3b",
    "Startup costs: $m":                          "#bdc3c7",
}

# Indicator options for Evolution & Zonal Comparison pages
INDICATOR_OPTIONS = [
    {"label": "Capacity (MW)",                  "value": "CapacityTechFuel"},
    {"label": "Energy Generation (GWh)",        "value": "EnergyTechFuelComplete"},
    {"label": "New Capacity (MW)",              "value": "NewCapacityTechFuel"},
    {"label": "New Capacity Cumulative (MW)",   "value": "NewCapacityTechFuelCumulated"},
    {"label": "Costs (m USD)",                  "value": "Costs"},
    {"label": "Generation Costs (USD/MWh)",     "value": "CostsPerMWh"},
    {"label": "CAPEX (m USD)",                  "value": "CapexInvestmentComponent"},
    {"label": "CAPEX Cumulative (m USD)",       "value": "CapexInvestmentComponentCumulated"},
    {"label": "Spinning Reserve (GWh)",         "value": "ReserveSpinningTechFuel"},
]

LINE_INDICATOR_OPTIONS = [
    {"label": "None",                           "value": ""},
    {"label": "Emissions (MtCO2)",              "value": "EmissionsZone"},
    {"label": "Emission Intensity (tCO2/GWh)",  "value": "EmissionsIntensityZone"},
    {"label": "Demand (GWh)",                   "value": "DemandEnergyZone"},
    {"label": "Peak Demand (MW)",               "value": "DemandPeakZone"},
    {"label": "Gen Cost (USD/MWh)",             "value": "GenCostsPerMWh"},
]

INDICATOR_LABELS = {o["value"]: o["label"] for o in INDICATOR_OPTIONS}
INDICATOR_LABELS.update({o["value"]: o["label"] for o in LINE_INDICATOR_OPTIONS})

# Which source file each indicator comes from, and which column is the legend
# source: 'techfuel' | 'costs' | 'capex'
INDICATOR_SOURCE = {
    "CapacityTechFuel":              ("techfuel", "techfuel"),
    "EnergyTechFuelComplete":        ("techfuel", "techfuel"),
    "NewCapacityTechFuel":           ("techfuel", "techfuel"),
    "NewCapacityTechFuelCumulated":  ("techfuel", "techfuel"),
    "ReserveSpinningTechFuel":       ("techfuel", "techfuel"),
    "Costs":                         ("costs",    "uni"),
    "CostsPerMWh":                   ("costs",    "uni"),
    "CapexInvestmentComponent":      ("capex",    "uni"),
    "CapexInvestmentComponentCumulated": ("capex", "uni"),
}

PLANT_INDICATOR_OPTIONS = [
    {"label": "Capacity (MW)",   "value": "CapacityPlant"},
    {"label": "Energy (GWh)",    "value": "EnergyPlant"},
    {"label": "Costs (m USD)",   "value": "CostsPlant"},
]

# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def get_available_models():
    """Return list of (model_type, region) tuples found under model_data/."""
    options = []
    if not DATA_ROOT.exists():
        return options
    for mt in DATA_ROOT.iterdir():
        if not mt.is_dir():
            continue
        for region in mt.iterdir():
            if region.is_dir() and (region / "scenarios").exists():
                options.append((mt.name, region.name))
    return options


def get_scenarios(model_type: str, region: str) -> list:
    scenarios_dir = DATA_ROOT / model_type / region / "scenarios"
    if not scenarios_dir.exists():
        return []
    return sorted(s.name for s in scenarios_dir.iterdir() if s.is_dir())


def get_zones(model_type: str, region: str) -> list:
    df = load_techfuel(model_type, region)
    if df.empty:
        return []
    return sorted(df["z"].unique().tolist())


def get_countries(model_type: str, region: str) -> list:
    df = load_techfuel(model_type, region)
    if df.empty:
        return []
    return sorted(df["c"].unique().tolist())


def get_years(model_type: str, region: str) -> list:
    df = load_techfuel(model_type, region)
    if df.empty:
        return []
    return sorted(df["y"].unique().tolist())

# ---------------------------------------------------------------------------
# Internal loader
# ---------------------------------------------------------------------------

def _load_csv(model_type: str, region: str, filename: str) -> pd.DataFrame:
    """Load a CSV for all scenarios, appending a 'scenario' column."""
    scenarios_dir = DATA_ROOT / model_type / region / "scenarios"
    dfs = []
    for scenario_dir in sorted(scenarios_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        csv_path = scenario_dir / "output_csv" / filename
        if csv_path.exists():
            df = pd.read_csv(csv_path, low_memory=False)
            df["scenario"] = scenario_dir.name
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

# ---------------------------------------------------------------------------
# Cached loaders (small-medium files)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def load_techfuel(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pTechFuelMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_costs(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pCostsMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_capex(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pCapexInvestmentMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_yearly_zone(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pYearlyZoneMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
    return df


@lru_cache(maxsize=32)
def load_transmission(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pTransmissionMerged.csv")
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # Normalise the counterpart-zone column to always be called 'z2'.
    # Variants across model outputs (may coexist after concat across scenarios):
    #   - 'z2'    : standard column (EAPP baseline)
    #   - 'uni.1' : pandas auto-renamed duplicate 'uni' column (EAPP ISO)
    #   - neither : counterpart zone is in 'uni' (CAPP)
    bilateral = {"Interchange", "InterconUtilization", "NetImport",
                 "TransmissionCapacity", "NewTransmissionCapacity",
                 "CongestionShare"}
    if "uni.1" in df.columns:
        # Fill z2 from uni.1 where z2 is missing (covers mixed baseline+ISO case)
        if "z2" not in df.columns:
            df["z2"] = df["uni.1"]
        else:
            df["z2"] = df["z2"].fillna(df["uni.1"])
        df = df.drop(columns=["uni.1"])
    if "z2" not in df.columns:
        # CAPP-style: uni holds the counterpart zone for bilateral attributes
        mask = df["attribute"].isin(bilateral)
        df["z2"] = np.where(mask, df["uni"], np.nan)
    return df


@lru_cache(maxsize=32)
def load_plants(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pPlantMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_npv(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pNetPresentCostSystemMerged.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_hourly_price(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pHourlyPrice.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@lru_cache(maxsize=32)
def load_zone_coords(model_type: str, region: str) -> dict:
    """Return {zone_name: (lat, lon)} from linestring_countries.geojson."""
    path = DATA_ROOT / model_type / region / "linestring_countries.geojson"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    coords = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        z = props.get("z")
        if z and z not in coords:
            coords[z] = (props["country_ini_lat"], props["country_ini_lon"])
    return coords


@lru_cache(maxsize=32)
def load_phours(model_type: str, region: str) -> dict:
    """Return {(q, d): pct_weight} from pHours.csv (baseline scenario preferred).

    pHours value = number of days the representative day represents.
    Weight = value / total_days * 100.
    """
    scenarios_dir = DATA_ROOT / model_type / region / "scenarios"
    if not scenarios_dir.exists():
        return {}
    # Try baseline first, then any scenario alphabetically
    candidates = sorted(scenarios_dir.iterdir(),
                        key=lambda p: (p.name != "baseline", p.name))
    for sc_dir in candidates:
        csv_path = sc_dir / "input" / "pHours.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            # One representative weight per (q, d) — take first since all t equal within a day
            unique_qd = df.groupby(["q", "d"])["value"].first()
            total = unique_qd.sum()
            if total <= 0:
                return {}
            return {(q, d): v / total * 100 for (q, d), v in unique_qd.items()}
    return {}


# Dispatch is heavy — no lru_cache, caller controls when it's loaded
def load_dispatch(model_type: str, region: str) -> pd.DataFrame:
    df = _load_csv(model_type, region, "pDispatchComplete.csv")
    if not df.empty:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

# ---------------------------------------------------------------------------
# Shared computation helpers
# ---------------------------------------------------------------------------

def apply_view_mode(df: pd.DataFrame, view: str, ref_scenario: str,
                    group_keys: list) -> pd.DataFrame:
    """
    Apply Absolute / Difference / Percentage transformation.
    df must have a 'scenario' column and a 'value' column.
    group_keys are the non-scenario columns to join on.
    """
    if view == "Absolute" or not ref_scenario:
        return df

    df_ref = (
        df[df["scenario"] == ref_scenario]
        .copy()
        .rename(columns={"value": "ref_value"})
        .drop(columns=["scenario"])
    )
    df_out = df.merge(df_ref, on=group_keys, how="left")
    df_out["ref_value"] = df_out["ref_value"].fillna(0)

    if view == "Difference":
        df_out["value"] = df_out["value"] - df_out["ref_value"]
    elif view == "Percentage":
        df_out["value"] = np.where(
            df_out["ref_value"] != 0,
            (df_out["value"] - df_out["ref_value"]) / df_out["ref_value"].abs() * 100,
            0,
        )
    return df_out.drop(columns=["ref_value"])


def get_color_sequence(categories: list) -> list:
    """Return ordered color list matching TECH_COLORS for given categories."""
    return [TECH_COLORS.get(c, "#aaaaaa") for c in categories]
