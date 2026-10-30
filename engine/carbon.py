"""Carbon accounting with two separate boundaries.

1. CBAM boundary (what the EU importer pays on, for iron and steel goods):
   direct emissions of the installation (fuel burnt on site) plus the embedded
   direct emissions of purchased precursors (pig iron; steel scrap carries none).
   Electricity (indirect) emissions are reported separately and are NOT priced
   for iron and steel under the EU CBAM.
2. Scope 1 + 2 footprint (for buyers' supply-chain reporting and India's CCTS view):
   fuel plus metered electricity at the CEA grid factor.

The passport is verification-ready data. An accredited verifier must verify it
before an importer uses it in a CBAM declaration.
"""
from . import config as K


def period_figures(heats, daily, days, grid_ef=K.GRID_EF_REPORTING):
    h = heats[heats.day.between(*days)]
    d = daily[daily.day.between(*days)]
    good_t, liquid_t = float(h.good_t.sum()), float(h.liquid_t.sum())
    mwh = float(d.plant_kwh.sum()) / 1000
    lpg_t = K.LPG_KG_PER_T_LIQUID * liquid_t * K.LPG_EF_KG_CO2_PER_KG / 1000
    pig_t = float((h.pig_iron_share * h.liquid_t).sum())
    scrap_t = float((h.steel_scrap_share * h.liquid_t).sum())
    precursor = pig_t * K.PIG_IRON_EF + scrap_t * K.STEEL_SCRAP_EF
    indirect = mwh * grid_ef
    return dict(
        period_days=list(days), good_t=good_t, liquid_t=liquid_t,
        electricity_mwh_per_t=mwh / good_t,
        pig_iron_share=pig_t / liquid_t, steel_scrap_share=scrap_t / liquid_t,
        direct_tco2_per_t=lpg_t / good_t,
        precursor_tco2_per_t=precursor / good_t,
        cbam_embedded_tco2_per_t=(lpg_t + precursor) / good_t,
        indirect_tco2_per_t=indirect / good_t,
        scope12_tco2_per_t=(lpg_t + indirect) / good_t,
        scope12_ccts_tco2_per_t=(lpg_t + mwh * K.GRID_EF_CCTS) / good_t,
    )


def passport(heats, daily, days, shipment_t, shipment_id):
    f = period_figures(heats, daily, days)
    return dict(
        passport_id=f"UK-PCP-{shipment_id}",
        installation="[Foundry name], Rajkot, Gujarat, India (example installation)",
        production_route="Electric induction furnace melting of steel scrap, pig iron and own returns; sand casting",
        product="Iron castings, machined (example)",
        cn_code="7326 90 98, other articles of iron or steel (in CBAM scope today; confirm classification per product)",
        cbam_note="Plain grey iron castings (CN 7325) enter CBAM only if the proposed 2028 downstream extension is adopted.",
        shipment_id=shipment_id, quantity_t=shipment_t, monitoring_period_days=f["period_days"],
        charge_mix=dict(pig_iron=f["pig_iron_share"], steel_scrap=f["steel_scrap_share"],
                        returns=1 - f["pig_iron_share"] - f["steel_scrap_share"]),
        specific_direct_tco2_per_t=f["direct_tco2_per_t"],
        specific_precursor_tco2_per_t=f["precursor_tco2_per_t"],
        specific_embedded_cbam_tco2_per_t=f["cbam_embedded_tco2_per_t"],
        embedded_cbam_tco2=f["cbam_embedded_tco2_per_t"] * shipment_t,
        indirect_reported_tco2_per_t=f["indirect_tco2_per_t"],
        electricity_mwh_per_t=f["electricity_mwh_per_t"],
        evidence=["Furnace and mains meter readings per heat (meter IDs FM-01, MM-01)",
                  "Heat log: charge weight and charge mix per heat",
                  "LPG purchase bills (OCR)", "Pig iron supplier certificates (embedded emissions)",
                  "Dispatch slip for the shipment"],
        factors=f"Pig iron {K.PIG_IRON_EF} tCO2/t (assumption: replace with supplier actual or EU default for CN 7201); "
                f"steel scrap 0; LPG {K.LPG_EF_KG_CO2_PER_KG} kgCO2/kg (IPCC 2006); grid {K.GRID_EF_REPORTING} tCO2/MWh (CEA v22.0), reported only",
        status="Verification-ready. Indirect emissions are reported, not priced, for iron and steel under the EU CBAM.",
    )
