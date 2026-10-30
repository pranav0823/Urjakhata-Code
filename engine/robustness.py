"""How robust are the savings, and how reliable is the drift alarm?

Two evaluations that reuse the simulator's own equations (sim.melt_kwh_per_t) in
vectorised form, so thousands of plant-years run in seconds:

1. Savings Monte Carlo. The 90-day simulation assumes operators adopt the full
   practice change. Here every uncertain input is drawn from a stated range:
   how much of the advice operators follow, how much of the compressed-air saving
   is realised, on how many days the melt plan is followed, furnace efficiency
   (BEE range), tariff level and kit cost. Output: P10 / P50 / P90 savings and
   payback, and savings against adherence.

2. Drift alarm reliability. Many simulated plant-months with and without faults:
   false alarms per month, detection delay for 2%, 5% and 10% faults, and the
   same test for a plain CUSUM on kWh/t that ignores logged practice.
"""
import numpy as np
from . import config as K
from . import sec
from .sim import melt_kwh_per_t

# Ranges sampled in the Monte Carlo (low, high), uniform. Edit here.
MC_RANGES = dict(
    practice_adherence=(0.25, 1.0),   # share of the advised practice change operators achieve
    compressor_realised=(0.25, 1.0),  # share of the leak-fix and timer saving realised
    tod_days_followed=(0.5, 1.0),     # share of days the melt plan is followed
    furnace_eff=(0.65, 0.75),         # BEE: 65 to 75% for induction furnaces
    tariff_level=(0.9, 1.1),          # FPPAS and duty move the energy rate
    kit_rs=(sum(b[1] for b in K.BOM), sum(b[2] for b in K.BOM)),
    subscription_rs_month=K.SUBSCRIPTION_RS_MONTH,
)


# ------------------------------------------------------------------ heat generator
def practice_mix(adherence):
    """Practice (mean, sd) after operators adopt a share of the advised change."""
    return {k: (b[0] + adherence * (K.PRACTICE_IMPROVED[k][0] - b[0]),
                b[1] + adherence * (K.PRACTICE_IMPROVED[k][1] - b[1]))
            for k, b in K.PRACTICE_BASELINE.items()}


def gen_heats(rng, n_days, practice, eff=K.FURNACE_EFF, heats_per_day=10, melt_mult=None):
    """Vectorised heat generator with the same equations and clipping as sim.plan_heats.
    melt_mult: optional per-heat multiplier on melting energy (used to inject faults)."""
    n = n_days * heats_per_day
    p = {k: rng.normal(m, s, n) for k, (m, s) in practice.items()}
    sh = np.maximum(2.0, p["superheat_c"])
    sl = np.clip(p["slag_pct"], 1.2, 5)
    lid = np.clip(p["lid_open"], 0.0, 0.8)
    hold = np.maximum(3.0, p["hold_min"])
    charge = np.clip(rng.normal(K.CHARGE_KG, 15, n), 450, 540)
    noise = rng.normal(1.0, K.MELT_NOISE_SD, n)
    t = charge / 1000
    melt_t = melt_kwh_per_t(eff, sh, sl, lid) * noise
    if melt_mult is not None:
        melt_t = melt_t * melt_mult
    first = (np.arange(n) % heats_per_day) == 0
    melt_kwh = t * melt_t * (1 + K.COLD_START_EXTRA * first)
    furnace_kwh = melt_kwh + K.HOLD_KW * hold / 60 + K.TAP_KW * K.TAP_MIN / 60
    return dict(day=np.arange(n) // heats_per_day + 1, superheat_c=sh, slag_pct=sl, charge_kg=charge,
                liquid_t=t, melt_sec=melt_t, furnace_kwh=furnace_kwh, hold_min=hold)


def sec_liquid(h):
    return h["furnace_kwh"].sum() / h["liquid_t"].sum()


# ------------------------------------------------------------------ compressor
def compressor_kwh_day(leak, timer):
    """Daily compressor kWh with the same load/unload model as sim.render_timeseries."""
    spd = 86400 // K.DT_S
    hour = np.arange(spd) * K.DT_S / 3600
    demand = np.where((hour >= 8) & (hour < 18), 0.45, 0.05) + leak
    running = ((hour >= K.CREW_WINDOW[0]) & (hour < K.CREW_WINDOW[1] + 1)) if timer else np.ones(spd, bool)
    phase = (np.arange(spd) * K.DT_S) % 120 / 120.0
    kw = np.where(phase < np.clip(demand, 0, 1), K.COMPRESSOR_LOAD_KW, K.COMPRESSOR_UNLOAD_KW) * running
    return float(kw.sum() * K.DT_S / 3600)


# ------------------------------------------------------------------ savings Monte Carlo
def full_adoption_check(seed=K.SEED, n_days=200):
    """Fast model at full adoption, to compare against the 90-day simulation."""
    rng = np.random.default_rng(seed)
    b = sec_liquid(gen_heats(rng, n_days, practice_mix(0.0)))
    i = sec_liquid(gen_heats(rng, n_days, practice_mix(1.0)))
    comp = (compressor_kwh_day(K.COMPRESSOR_LEAK_BEFORE, False) - compressor_kwh_day(K.COMPRESSOR_LEAK_AFTER, True))
    return dict(sec_baseline=b, sec_improved=i, furnace_kwh_saved=(b - i) * K.ANNUAL_LIQUID_TONNES,
                compressor_kwh_saved=comp * K.OPERATING_DAYS_PER_YEAR)


def _one(rng, a, c, d, eff, tl, kit, sub, ref, n_days):
    b = sec_liquid(gen_heats(rng, n_days, practice_mix(0.0), eff))
    i = sec_liquid(gen_heats(rng, n_days, practice_mix(a), eff))
    furnace = (b - i) * K.ANNUAL_LIQUID_TONNES
    comp = c * ref["compressor_kwh_saved_full"]
    aux = a * ref["aux_kwh_saved_full"]
    kwh = furnace + comp + aux
    rs_energy = kwh * ref["avg_rate"] * tl
    rs_tod = d * ref["tod_rs_full"]
    rs = rs_energy + rs_tod
    yr1 = kit + 12 * sub
    return dict(practice_adherence=a, compressor_realised=c, tod_days_followed=d, furnace_eff=eff, tariff_level=tl,
                kit_rs=kit, subscription_rs_month=sub, furnace_kwh=furnace, compressor_kwh=comp, aux_kwh=aux,
                kwh=kwh, rs_energy=rs_energy, rs_tod=rs_tod, rs=rs, tco2=kwh / 1000 * K.GRID_EF_REPORTING,
                payback_months=12 * yr1 / rs)


def _draw(rng, key):
    lo, hi = MC_RANGES[key]
    return float(rng.uniform(lo, hi))


def savings_monte_carlo(ref, n=1000, seed=K.SEED + 100, n_days=100):
    """ref: values from the full simulation (avg_rate, tod_rs_full, compressor and aux kWh at full adoption)."""
    rng = np.random.default_rng(seed)
    rows = [_one(rng, _draw(rng, "practice_adherence"), _draw(rng, "compressor_realised"),
                 _draw(rng, "tod_days_followed"), _draw(rng, "furnace_eff"), _draw(rng, "tariff_level"),
                 _draw(rng, "kit_rs"), _draw(rng, "subscription_rs_month"), ref, n_days) for _ in range(n)]
    keys = ["kwh", "rs", "rs_energy", "rs_tod", "tco2", "payback_months", "furnace_kwh"]
    pct = {k: {f"p{q}": float(np.percentile([r[k] for r in rows], q)) for q in (10, 50, 90)} for k in keys}
    pb = np.array([r["payback_months"] for r in rows])
    # stress case: every input at its unfavourable end
    s = MC_RANGES
    stress = _one(np.random.default_rng(seed + 1), s["practice_adherence"][0], s["compressor_realised"][0],
                  s["tod_days_followed"][0], s["furnace_eff"][0], s["tariff_level"][0], s["kit_rs"][1],
                  s["subscription_rs_month"][1], ref, 200)
    # which input moves the rupees most (rank correlation)
    rs = np.array([r["rs"] for r in rows])
    drivers = {}
    for k in ["practice_adherence", "compressor_realised", "tod_days_followed", "furnace_eff", "tariff_level"]:
        x = np.array([r[k] for r in rows])
        drivers[k] = float(np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(rs)))[0, 1])
    return dict(n=n, ranges={k: list(v) for k, v in MC_RANGES.items()}, percentiles=pct,
                share_payback_under_6m=float((pb <= 6).mean()), share_payback_under_12m=float((pb <= 12).mean()),
                stress_case=stress, drivers=drivers,
                samples=[{k: round(r[k], 4) for k in ("practice_adherence", "rs", "payback_months")} for r in rows[:400]])


def adherence_curve(ref, levels=np.linspace(0, 1, 11), n=200, seed=K.SEED + 200, n_days=60):
    """Savings band (P10, P50, P90) at fixed practice adherence, other inputs sampled."""
    rng = np.random.default_rng(seed)
    out = []
    for a in levels:
        rows = [_one(rng, float(a), _draw(rng, "compressor_realised"), _draw(rng, "tod_days_followed"),
                     _draw(rng, "furnace_eff"), _draw(rng, "tariff_level"), _draw(rng, "kit_rs"),
                     _draw(rng, "subscription_rs_month"), ref, n_days) for _ in range(n)]
        rs = [r["rs"] for r in rows]
        pb = [r["payback_months"] for r in rows]
        out.append(dict(adherence=float(a), rs_p10=float(np.percentile(rs, 10)), rs_p50=float(np.percentile(rs, 50)),
                        rs_p90=float(np.percentile(rs, 90)), payback_p50=float(np.percentile(pb, 50)),
                        payback_p90=float(np.percentile(pb, 90))))
    return out


# ------------------------------------------------------------------ drift alarm reliability
def _cusum_alarms(z, k=K.CUSUM_K, h=K.CUSUM_H):
    """Indices where a one-sided CUSUM on standardised residuals z alarms (reset after each alarm)."""
    s, hits = 0.0, []
    for i, v in enumerate(z):
        s = max(0.0, s + v - k)
        if s > h:
            hits.append(i)
            s = 0.0
    return hits


def _detectors(ref, mon):
    """Standardised series for the residual detector (UrjaKhata) and a plain kWh/t detector."""
    X = lambda h: np.column_stack([np.ones(len(h["melt_sec"]))] + [h[c] for c in sec.DRIFT_X])
    beta, *_ = np.linalg.lstsq(X(ref), ref["melt_sec"], rcond=None)
    r_ref = ref["melt_sec"] - X(ref) @ beta
    sd = r_ref.std(ddof=len(sec.DRIFT_X) + 1)
    z_resid = (mon["melt_sec"] - X(mon) @ beta) / sd
    z_raw = (mon["melt_sec"] - ref["melt_sec"].mean()) / ref["melt_sec"].std(ddof=1)
    return {"residual": z_resid, "raw": z_raw}


def drift_reliability(runs=400, seed=K.SEED + 300, ref_days=15, mon_days=30, onset_day=10, ramp_days=8, h=K.CUSUM_H):
    """Simulated plant-months. Scenarios: no fault; operators slip back on practice
    (not an equipment fault, so an equipment alarm should stay quiet); and lining or
    coil wear raising melting energy by 2%, 5% or 10% (ramped over ramp_days)."""
    rng = np.random.default_rng(seed)
    hpd = 10
    good = practice_mix(1.0)
    slip = dict(good, superheat_c=(22, 5), slag_pct=(2.8, 0.35))
    onset = onset_day * hpd
    n_mon = mon_days * hpd
    w = np.clip((np.arange(n_mon) - onset + 1) / (ramp_days * hpd), 0, 1)
    scen = {"no_fault": None, "practice_slip": None, "fault_2pct": 0.02, "fault_5pct": 0.05, "fault_10pct": 0.10}
    res = {}
    for name, size in scen.items():
        stats = {d: dict(alarm_runs=0, false_before_onset=0, detected=0, delays=[]) for d in ("residual", "raw")}
        for _ in range(runs):
            ref = gen_heats(rng, ref_days, good)
            if name == "practice_slip":
                a = gen_heats(rng, onset_day, good)
                b = gen_heats(rng, mon_days - onset_day, slip)
                mon = {k: np.concatenate([a[k], b[k]]) for k in a}
            else:
                mult = None if size is None else 1 + size * w
                mon = gen_heats(rng, mon_days, good, melt_mult=mult)
            for det, z in _detectors(ref, mon).items():
                hits = _cusum_alarms(z, K.CUSUM_K, h)
                st = stats[det]
                if hits:
                    st["alarm_runs"] += 1
                if size is not None:
                    if any(i < onset for i in hits):
                        st["false_before_onset"] += 1
                    after = [i for i in hits if i >= onset]
                    if after:
                        st["detected"] += 1
                        st["delays"].append(after[0] - onset + 1)
        out = {}
        for det, st in stats.items():
            d = dict(alarm_share=st["alarm_runs"] / runs)
            if size is not None:
                d.update(detect_share=st["detected"] / runs,
                         false_before_onset_share=st["false_before_onset"] / runs,
                         delay_heats_p50=float(np.median(st["delays"])) if st["delays"] else None,
                         delay_heats_p90=float(np.percentile(st["delays"], 90)) if st["delays"] else None)
            out[det] = d
        res[name] = out
    return dict(runs=runs, ref_days=ref_days, mon_days=mon_days, onset_day=onset_day, ramp_days=ramp_days,
                heats_per_day=hpd, k_sigma=K.CUSUM_K, h_sigma=h, scenarios=res)


def threshold_sweep(levels=(5, 6, 7, 8, 9), runs=400):
    """False alarms against detection delay for the residual detector at several thresholds."""
    out = []
    for h in levels:
        s = drift_reliability(runs=runs, h=float(h))["scenarios"]
        out.append(dict(h=float(h), false_alarm_month=s["no_fault"]["residual"]["alarm_share"],
                        slip_alarm=s["practice_slip"]["residual"]["alarm_share"],
                        delay_2=s["fault_2pct"]["residual"]["delay_heats_p50"],
                        delay_5=s["fault_5pct"]["residual"]["delay_heats_p50"],
                        delay_10=s["fault_10pct"]["residual"]["delay_heats_p50"]))
    return out


# ------------------------------------------------------------------ NILM across independent renders
def nilm_seeds(heats, seeds=(11, 12, 13, 14, 15)):
    """Re-render the auxiliary loads with different random seeds (same heat log), retrain
    and retest. One render is one draw; the spread shows how much a single number can move.
    Protocols: commissioning labels only (days 1-4), and commissioning plus one re-labelled
    day when the melt schedule changes (the product rule)."""
    from .sim import render_timeseries
    from .nilm import HybridNILM, ShareBaseline, evaluate
    a, b = K.NILM_TRAIN_DAYS
    tests = {"days_5_7": ((5, 7), False), "days_80_82_no_relabel": ((80, 82), False), "days_80_82": ((80, 82), True)}
    rows = []
    for s in seeds:
        ts, loads = render_timeseries(heats, np.random.default_rng(s), days=82)
        tr0 = ts.day.between(a, b)
        tr1 = tr0 | (ts.day == K.NILM_RELABEL_DAY)
        fitted = {False: (HybridNILM(loads).fit(ts[tr0]), ShareBaseline(loads).fit(ts[tr0])),
                  True: (HybridNILM(loads).fit(ts[tr1]), ShareBaseline(loads).fit(ts[tr1]))}
        for name, ((d0, d1), relabel) in tests.items():
            m, nv = fitted[relabel]
            part = ts[ts.day.between(d0, d1)]
            ev, evn = evaluate(part, m.predict(part), loads), evaluate(part, nv.predict(part), loads)
            for i, r in ev.reset_index(drop=True).iterrows():
                rows.append(dict(seed=s, test=name, load=r["load"], sae=float(r["sae"]), f1=float(r["f1_on_off"]),
                                 naive_sae=float(evn.sae.iloc[i]), naive_f1=float(evn.f1_on_off.iloc[i])))
    out = {}
    for name in tests:
        rs = [r for r in rows if r["test"] == name]
        mx = [max(r["sae"] for r in rs if r["seed"] == s) for s in seeds]
        mxn = [max(r["naive_sae"] for r in rs if r["seed"] == s) for s in seeds]
        mean_s = [np.mean([r["sae"] for r in rs if r["seed"] == s]) for s in seeds]
        mean_n = [np.mean([r["naive_sae"] for r in rs if r["seed"] == s]) for s in seeds]
        out[name] = dict(
            max_sae_median=float(np.median(mx)), max_sae_worst=float(max(mx)), max_sae_naive_median=float(np.median(mxn)),
            mean_sae_median=float(np.median(mean_s)), mean_sae_naive_median=float(np.median(mean_n)),
            mean_sae_range=[float(min(mean_s)), float(max(mean_s))],
            mean_f1=float(np.mean([r["f1"] for r in rs])), mean_f1_naive=float(np.mean([r["naive_f1"] for r in rs])),
            per_load={l: dict(sae_median=float(np.median([r["sae"] for r in rs if r["load"] == l])),
                              sae_worst=float(max(r["sae"] for r in rs if r["load"] == l)),
                              naive_sae_median=float(np.median([r["naive_sae"] for r in rs if r["load"] == l])))
                      for l in sorted({r["load"] for r in rs})})
    return dict(seeds=list(seeds), tests=out)
