import numpy as np
from engine import sim, tod, mv, sec, carbon, tariff, config as K
from engine.nilm import HybridNILM, ShareBaseline, evaluate


def heats():
    return sim.plan_heats(np.random.default_rng(K.SEED))


def test_baseline_sec_inside_bee_range():
    h = heats()
    b = h[h.day <= K.BASELINE_DAYS]
    assert 600 <= b.furnace_kwh.sum() / b.liquid_t.sum() <= 750      # BEE foundry mapping: 600-750 kWh/t


def test_melt_time_matches_bee_example():
    h = heats()
    assert 28 <= h[h.first_heat == 0].melt_min.mean() <= 40           # BEE: about 35 min at full power


def test_practice_lowers_sec_without_cutting_output():
    h = heats()
    b, r = h[h.day <= K.BASELINE_DAYS], h[h.day.between(40, 57)]
    assert r.furnace_kwh.sum() / r.liquid_t.sum() < b.furnace_kwh.sum() / b.liquid_t.sum()
    assert abs(r.groupby("day").liquid_t.sum().mean() - b.groupby("day").liquid_t.sum().mean()) < 0.2


def test_gujarat_effective_rates():
    assert abs(tariff.rate("GJ", 3) - 7.953) < 0.01       # (4.20 + 2.45) x 1.0399 x 1.15
    assert abs(tariff.rate("GJ", 8) - 8.969) < 0.01       # morning peak +0.85
    assert abs(tariff.rate("GJ", 13) - 7.235) < 0.01      # solar hours -0.60


def test_tod_plan_respects_constraints_and_saves():
    prof = tod.heat_profile(290.0, 32.0, 8.0, 8.0)
    plan = tod.optimise_day(10, prof, "GJ")
    s = plan["start_hours"]
    dur = len(prof) * tod.SLOT_MIN / 60
    assert len(s) == 10
    assert all(b - a >= dur - 1e-9 for a, b in zip(s, s[1:]))
    assert s[0] >= K.CREW_WINDOW[0] and s[-1] + dur <= K.CREW_WINDOW[1]
    for a, b in K.SHIFTS:
        assert sum(1 for x in s if a <= x < b) <= K.MAX_HEATS_PER_SHIFT
    assert plan["plan_cost_rs"] < tod.habitual_cost(10, prof, "GJ")


def test_mv_option_b_has_band():
    res = mv.option_b(heats())
    assert res["savings_kwh"] > 0 and res["savings_low_kwh"] < res["savings_kwh"] < res["savings_high_kwh"]


def test_drift_detector_fires_after_fault_only():
    h = heats()
    alert, _, _, _ = sec.cusum_drift(h, (K.TOD_START_DAY, K.LINING_WEAR_START_DAY - 1))
    assert alert is not None and alert["day"] >= K.LINING_WEAR_START_DAY


def test_cbam_boundary_excludes_electricity():
    import pandas as pd
    h = heats()
    daily = pd.DataFrame({"day": range(1, K.DAYS + 1), "plant_kwh": 4000.0})
    f = carbon.period_figures(h, daily, (1, 28))
    assert abs(f["cbam_embedded_tco2_per_t"] - (f["direct_tco2_per_t"] + f["precursor_tco2_per_t"])) < 1e-9
    assert f["indirect_tco2_per_t"] > 0


def test_nilm_beats_naive_on_timing():
    h = heats()
    ts, loads = sim.render_timeseries(h, np.random.default_rng(1), days=3)
    m = HybridNILM(loads).fit(ts[ts.day <= 2])
    n = ShareBaseline(loads).fit(ts[ts.day <= 2])
    part = ts[ts.day == 3]
    ev, evn = evaluate(part, m.predict(part), loads), evaluate(part, n.predict(part), loads)
    assert ev.f1_on_off.mean() > evn.f1_on_off.mean()
    assert ev.sae.max() < 0.25


# ---- robustness checks (engine/robustness.py) ----
from engine import robustness as R

REF = dict(avg_rate=8.02, tod_rs_full=213000.0, compressor_kwh_saved_full=30150.0, aux_kwh_saved_full=5300.0)


def test_fast_model_matches_full_simulation():
    h = heats()
    b = h[h.day <= K.BASELINE_DAYS]
    sim_b = b.furnace_kwh.sum() / b.liquid_t.sum()
    fast = R.full_adoption_check()
    assert abs(fast["sec_baseline"] / sim_b - 1) < 0.01
    assert fast["compressor_kwh_saved"] == (256.75 - 156.25) * K.OPERATING_DAYS_PER_YEAR


def test_savings_pay_back_within_a_year_even_in_stress_case():
    mc = R.savings_monte_carlo(REF, n=150)
    assert mc["percentiles"]["rs"]["p10"] < mc["percentiles"]["rs"]["p50"] < mc["percentiles"]["rs"]["p90"]
    assert mc["stress_case"]["payback_months"] < 12


def test_drift_alarm_rarely_false_and_catches_faults():
    d = R.drift_reliability(runs=120)["scenarios"]
    assert d["no_fault"]["residual"]["alarm_share"] < 0.10
    assert d["fault_5pct"]["residual"]["detect_share"] > 0.95


def test_residual_alarm_does_not_blame_equipment_for_practice_slip():
    d = R.drift_reliability(runs=120)["scenarios"]["practice_slip"]
    assert d["residual"]["alarm_share"] < 0.5 < d["raw"]["alarm_share"]


def test_nilm_options_for_other_plants():
    """Thresholds and sub-meter use are parameters, so the same model runs on other factories (engine/realdata.py)."""
    h = heats()
    ts, loads = sim.render_timeseries(h, np.random.default_rng(2), days=2)
    m = HybridNILM(loads, use_metered=False).fit(ts[ts.day == 1])
    part = ts[ts.day == 2]
    ev = evaluate(part, m.predict(part), loads, on_kw={k: 0.5 for k in loads})
    assert len(ev) == len(loads) and ev.f1_on_off.notna().all()
