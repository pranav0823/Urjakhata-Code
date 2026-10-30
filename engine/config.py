"""All plant, tariff and emission parameters for the UrjaKhata prototype.

Each value is either SOURCED (taken from a cited document) or an ASSUMPTION
(a labelled engineering estimate to be replaced with site data). The
PARAMS table at the bottom is exported to the website's "Sources and
assumptions" panel, so every number on screen can be traced.
Verified against sources as of October 2026.
"""

SEED = 7

# ---- Simulation horizon -------------------------------------------------
DAYS = 90                  # operating days
BASELINE_DAYS = 28         # 4-week baseline (meters installed, no changes)
SOP_START_DAY = 29         # owner starts acting on the daily briefings
COMPRESSOR_FIX_DAY = 36    # leak repair plus night shutdown timer
TOD_START_DAY = 43         # melts follow the optimised Time-of-Day plan
DT_S = 10                  # prototype resolution (product design: 1 s power reads)
OPERATING_DAYS_PER_YEAR = 300
NILM_TRAIN_DAYS = (1, 4)    # commissioning: portable clamp meters on each machine
NILM_RELABEL_DAY = TOD_START_DAY   # clamps go back on for one day whenever the melt schedule changes

# ---- Induction furnace (BEE Best Operating Practices, Belgaum foundry cluster)
CHARGE_KG = 500            # 500 kg coreless furnace
RATED_KW = 550             # BEE worked example: 500 kg, 550 kW, melt in about 35 min at full power
FURNACE_EFF = 0.72         # BEE: typical furnace efficiency 65-75% (older units); new units 81-87%
THEORETICAL_KWH_T = 396    # BEE: energy to melt and heat iron to 1,500 C
SUPERHEAT_KWH_T_PER_C = 0.5   # BEE: about 25 kWh/t per 50 C of superheat, at the meter
SLAG_KWH_T_PER_PCT = 10    # BEE: 10 kWh/t for every 1% slag
LID_OPEN_KWH_T_FULL = 25   # BEE: an uncovered 500 kg crucible loses up to 25 kWh/t
HOLD_KW = 60               # ASSUMPTION: power to hold a full 500 kg bath at temperature
TAP_MIN, TAP_KW = 10, 5
CHARGE_GAP_MIN = 10        # ASSUMPTION: recharging between heats
COLD_START_EXTRA = 0.20    # BEE: cold-start cycle should not exceed 120% of normal
HEATS_PER_DAY = (9, 10, 11)   # mean 10 heats: 5 t liquid a day, 1,500 t a year
HEATS_PATTERN = (10, 9, 11, 10, 11, 10, 9)   # weekly order pattern, mean 10, same in every period
CUSUM_K, CUSUM_H = 0.5, 8.0   # drift alarm: slack and threshold in residual SDs; h chosen by the false-alarm sweep in engine/robustness.py
MELT_NOISE_SD = 0.015        # ASSUMPTION: heat-to-heat variation not explained by logged variables (scrap density, moisture)

# Operating practice per heat: (mean, sd). Practice changes need no capital spend.
PRACTICE_BASELINE = dict(superheat_c=(25, 6), slag_pct=(3.0, 0.4), lid_open=(0.35, 0.08), hold_min=(18, 6))
PRACTICE_IMPROVED = dict(superheat_c=(12, 4), slag_pct=(2.3, 0.3), lid_open=(0.10, 0.05), hold_min=(8, 3))
ADOPTION_RAMP_DAYS = 6

# Charge mix per heat (share of charge weight). Pig iron is the CBAM precursor that matters.
CHARGE_MIX = dict(pig_iron=(0.20, 0.03), steel_scrap=(0.45, 0.04))   # remainder: own foundry returns

# Hidden fault used to test the drift detector
LINING_WEAR_START_DAY = 58
LINING_WEAR_MAX_EFF_DROP = 0.05   # efficiency falls by up to 5 points (scenario)
LINING_WEAR_RAMP_DAYS = 8
RELINE_LAG_DAYS = 3

# ---- Yield and quality (ASSUMPTIONS, editable on the website) -------------
YIELD = 0.70
REJECT_RATE = (0.050, 0.008)

# ---- Auxiliary loads (ASSUMPTIONS, typical small grey-iron foundry) --------
AUX = {"cooling_pump": 11.0, "fume_extraction": 7.4, "sand_mixer": 15.0,
       "shot_blast": 22.0, "grinders": 5.5, "lighting_office": 4.0}
COMPRESSOR_LOAD_KW, COMPRESSOR_UNLOAD_KW = 15.0, 4.5
COMPRESSOR_LEAK_BEFORE, COMPRESSOR_LEAK_AFTER = 0.32, 0.10   # ASSUMPTION: share of capacity lost to leaks

# ---- Production shifts and scheduling constraints ---------------------------
CREW_WINDOW = (6, 23)        # melting and pouring only while the moulding line is staffed
SHIFTS = [(6, 14), (14, 23)] # shift A and shift B (with one hour overtime)
MAX_HEATS_PER_SHIFT = 7
BASELINE_FIRST_HEAT_H = 8.0  # habitual: first heat at 08:00, back to back

# ---- Tariffs (HT industrial, FY 2026-27). Effective variable rate per kWh is computed in tariff.py
TARIFFS = {
    "GJ": dict(
        name="Gujarat: PGVCL HTP-I (Rajkot)", short="Gujarat (Rajkot)",
        energy=4.20,              # Rs/kWh, billing demand 500-2,500 kVA
        windows=[(7, 11, 0.85, "abs", "peak"), (11, 17, -0.60, "abs", "solar"), (18, 22, 0.85, "abs", "peak")],
        fuel=2.45, fuel_var=0.0399, duty=0.15,
        demand=dict(contract_kva=600, note="Rs 150/kVA first 500 + Rs 260/kVA next 500; billed on max(MD, 85% of CD)"),
        source="GERC tariff schedule for PGVCL w.e.f. 1 Apr 2026 (energy 420 paise, peak +85 paise 07-11 and 18-22, solar -60 paise 11-17); FPPAS Rs 2.45/kWh + 3.99% from Jul 2026 (GUVNL, secondary); electricity duty 15% (Gujarat Electricity Duty Act)",
        confidence="Energy and ToU: primary. FPPAS: secondary, confirm against GUVNL circular."),
    "MH": dict(
        name="Maharashtra: MSEDCL HT I(A) (Kolhapur)", short="Maharashtra (Kolhapur)",
        energy=7.11,
        windows=[(9, 17, -0.25, "pct", "solar"), (17, 24, 0.25, "pct", "peak")],
        fuel=0.0, fuel_var=0.0, duty=0.0,
        demand=dict(contract_kva=600, note="Demand charge excluded"),
        source="MERC FY 2026-27 MYT framework: solar-hours rebate 09-17 (25% Oct-Mar, 15% Apr-Sep), peak 17-24 +25% for HT industrial; energy charge Rs 7.11/kVAh (sources conflict: 7.11 vs 7.48)",
        confidence="Uncertain: energy charge figures conflict; excludes FAC, wheeling and duty. Sensitivity case only."),
    "TN": dict(
        name="Tamil Nadu: TNPDCL HT I-A (Coimbatore)", short="Tamil Nadu (Coimbatore)",
        energy=7.50,
        windows=[(6, 10, 0.25, "pct", "peak"), (18, 22, 0.25, "pct", "peak"), (22, 24, -0.05, "pct", "night"), (0, 5, -0.05, "pct", "night")],
        fuel=0.0, fuel_var=0.0, duty=0.05,
        demand=dict(contract_kva=600, note="Rs 589/kVA a month; excluded from the variable rate"),
        source="TNERC FY 2025-26 order via TECA circular: Rs 7.50/kWh, peak 06-10 and 18-22 +25%, night 22-05 -5%, 5% electricity tax",
        confidence="FY 2025-26 values; FY 2026-27 revision not confirmed. Sensitivity case only."),
}
BASE_STATE = "GJ"

# ---- Emissions ----------------------------------------------------------
GRID_EF_REPORTING = 0.675    # CEA CO2 Baseline Database v22.0 (Aug 2026), FY 2025-26 weighted average
GRID_EF_CCTS = 0.727         # FY 2023-24 factor used for CCTS baselines
LPG_KG_PER_T_LIQUID = 3.0    # ASSUMPTION: ladle preheating, from LPG bills
LPG_EF_KG_CO2_PER_KG = 2.983 # IPCC 2006 default for LPG
PIG_IRON_EF = 1.80           # ASSUMPTION: embedded direct emissions of purchased pig iron, tCO2/t (use supplier actual or EU default for CN 7201)
STEEL_SCRAP_EF = 0.0         # CBAM: scrap carries no embedded emissions
ANNUAL_LIQUID_TONNES = 1500

# ---- Hardware and pricing (for the feasibility view) ------------------------
BOM = [
    ("Class 1 Modbus RS485 energy meters (3 nos), e.g. Schneider EasyLogic PM2220", 60000, 90000, "IndiaMART listings about Rs 19,000 to 30,000 each"),
    ("CTs: 1000/5 A for furnace feeder, 400/5 A for mains share, 100/5 A for compressor", 9000, 15000, "Estimate"),
    ("4G industrial gateway with store-and-forward (Teltonika or Advantech class)", 15000, 25000, "Estimate"),
    ("Panel work, shielded RS485 cabling, surge protection, installation", 15000, 20000, "Estimate"),
]
SUBSCRIPTION_RS_MONTH = (1500, 2500)
PASSPORT_TIER_RS_MONTH = (5000, 10000)


def _p(key, value, unit, status, source):
    return dict(key=key, value=value, unit=unit, status=status, source=source)


PARAMS = [
    _p("Furnace", "500 kg, 550 kW coreless induction", "", "sourced", "BEE Best Operating Practices (BOP), Belgaum foundry cluster: worked example"),
    _p("Theoretical melt energy", 396, "kWh/t", "sourced", "BEE BOP: iron to 1,500 C"),
    _p("Furnace efficiency", FURNACE_EFF, "", "sourced", "BEE BOP: 65-75% typical older units"),
    _p("Superheat penalty", SUPERHEAT_KWH_T_PER_C, "kWh/t per C", "sourced", "BEE BOP: 25 kWh/t per 50 C"),
    _p("Slag penalty", SLAG_KWH_T_PER_PCT, "kWh/t per 1% slag", "sourced", "BEE BOP"),
    _p("Open-lid loss", LID_OPEN_KWH_T_FULL, "kWh/t when fully open", "sourced", "BEE BOP: up to 25 kWh/t for a 500 kg crucible"),
    _p("Cold start", "+20% cycle time", "", "sourced", "BEE BOP: not above 120% of normal cycle"),
    _p("Holding power", HOLD_KW, "kW", "assumption", "Engineering estimate for a 500 kg bath"),
    _p("Yield, liquid to castings", YIELD, "", "assumption", "Typical grey-iron foundry; editable"),
    _p("Casting rejects", REJECT_RATE[0], "", "assumption", "Typical; held constant to prove quality is not traded"),
    _p("Compressed-air leaks", f"{COMPRESSOR_LEAK_BEFORE:.0%} to {COMPRESSOR_LEAK_AFTER:.0%}", "of capacity", "assumption", "Typical Indian SME range; confirm by leak survey"),
    _p("Pig iron share of charge", CHARGE_MIX["pig_iron"][0], "", "assumption", "Typical grey-iron charge; logged per heat"),
    _p("Pig iron embedded emissions", PIG_IRON_EF, "tCO2/t", "assumption", "Replace with supplier actual or EU default for CN 7201"),
    _p("LPG for ladle preheating", LPG_KG_PER_T_LIQUID, "kg/t liquid", "assumption", "From LPG bills (OCR)"),
    _p("LPG emission factor", LPG_EF_KG_CO2_PER_KG, "kgCO2/kg", "sourced", "IPCC 2006"),
    _p("Grid factor (reporting)", GRID_EF_REPORTING, "tCO2/MWh", "sourced", "CEA CO2 Baseline Database v22.0, FY 2025-26"),
    _p("Grid factor (CCTS view)", GRID_EF_CCTS, "tCO2/MWh", "sourced", "FY 2023-24 factor used for CCTS baselines"),
    _p("Tariff base case", "PGVCL HTP-I, FY 2026-27", "", "sourced", TARIFFS["GJ"]["source"]),
    _p("Drift alarm threshold", CUSUM_H, "residual SDs (slack 0.5)", "design", "Chosen by simulation: false alarms in 3% of plant-months; see the robustness panel"),
    _p("Annual output", ANNUAL_LIQUID_TONNES, "t liquid metal", "assumption", "About 1,000 t good castings at 70% yield, 5% rejects"),
]
