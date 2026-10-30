"""Digital twin of a small induction-furnace grey-iron foundry.

Heat energy follows the BEE Best Operating Practices rules at the meter:
    kWh/t = 396 / efficiency + 0.5 x excess superheat + 10 x slag% + 25 x lid-open share + holding
with a 20% longer melt on the first (cold) heat of the day. The simulator also
logs the charge mix of every heat and renders 10-second power channels for the
mains meter, the two sub-meters and the hidden auxiliary machines that NILM
must recover from the residual.
"""
import numpy as np
import pandas as pd
from . import config as K


def _blend(day, a, b):
    if day < K.SOP_START_DAY:
        return a
    w = min(1.0, (day - K.SOP_START_DAY + 1) / K.ADOPTION_RAMP_DAYS)
    return a + w * (b - a)


def melt_kwh_per_t(eff, superheat_c, slag_pct, lid_open):
    return (K.THEORETICAL_KWH_T / eff + K.SUPERHEAT_KWH_T_PER_C * superheat_c
            + K.SLAG_KWH_T_PER_PCT * slag_pct + K.LID_OPEN_KWH_T_FULL * lid_open)


def heat_energy(charge_kg, superheat_c, slag_pct, lid_open, hold_min, eff, first_of_day, noise=1.0):
    """Return melt minutes and energy split for one heat (kWh at the furnace meter)."""
    t = charge_kg / 1000
    melt_kwh = t * melt_kwh_per_t(eff, superheat_c, slag_pct, lid_open) * noise
    cold = 0.0
    if first_of_day:
        cold = melt_kwh * K.COLD_START_EXTRA     # cold crucible: 20% longer at full power
        melt_kwh += cold
    melt_min = melt_kwh / K.RATED_KW * 60
    hold_kwh = K.HOLD_KW * hold_min / 60
    tap_kwh = K.TAP_KW * K.TAP_MIN / 60
    return melt_min, melt_kwh, hold_kwh, tap_kwh, cold


def eff_for_day(day, reline_day):
    eff = K.FURNACE_EFF
    if day >= K.LINING_WEAR_START_DAY and (reline_day is None or day < reline_day):
        w = min(1.0, (day - K.LINING_WEAR_START_DAY + 1) / K.LINING_WEAR_RAMP_DAYS)
        eff -= K.LINING_WEAR_MAX_EFF_DROP * w
    return eff


def plan_heats(rng, reline_day=None, tod_starts=None):
    """Heat log for all days. tod_starts: {n_heats: [start hours]} used from TOD_START_DAY."""
    rows = []
    for day in range(1, K.DAYS + 1):
        n = K.HEATS_PATTERN[(day - 1) % len(K.HEATS_PATTERN)]
        eff = eff_for_day(day, reline_day)
        use_tod = tod_starts is not None and day >= K.TOD_START_DAY
        planned = sorted(tod_starts[n]) if use_tod else None
        clock = planned[0] * 60 if use_tod else K.BASELINE_FIRST_HEAT_H * 60
        for h in range(n):
            p = {}
            for key in K.PRACTICE_BASELINE:
                m = _blend(day, K.PRACTICE_BASELINE[key][0], K.PRACTICE_IMPROVED[key][0])
                s = _blend(day, K.PRACTICE_BASELINE[key][1], K.PRACTICE_IMPROVED[key][1])
                p[key] = rng.normal(m, s)
            p["superheat_c"] = max(2.0, p["superheat_c"])
            p["slag_pct"] = float(np.clip(p["slag_pct"], 1.2, 5))
            p["lid_open"] = float(np.clip(p["lid_open"], 0.0, 0.8))
            p["hold_min"] = max(3.0, p["hold_min"])
            charge = float(np.clip(rng.normal(K.CHARGE_KG, 15), 450, 540))
            pig = float(np.clip(rng.normal(*K.CHARGE_MIX["pig_iron"]), 0.08, 0.35))
            scrap = float(np.clip(rng.normal(*K.CHARGE_MIX["steel_scrap"]), 0.25, 0.65))
            noise = float(rng.normal(1.0, K.MELT_NOISE_SD))
            melt_min, melt_kwh, hold_kwh, tap_kwh, cold = heat_energy(
                charge, p["superheat_c"], p["slag_pct"], p["lid_open"], p["hold_min"], eff, h == 0, noise)
            start = max(clock, planned[h] * 60) if use_tod and h < len(planned) else clock
            dur = melt_min + p["hold_min"] + K.TAP_MIN
            rows.append(dict(
                day=day, heat_no=h + 1, heat_id=f"D{day:02d}-H{h + 1:02d}", charge_kg=charge,
                pig_iron_share=pig, steel_scrap_share=scrap, returns_share=max(0.0, 1 - pig - scrap),
                start_min=start, melt_min=melt_min, hold_min=p["hold_min"], end_min=start + dur,
                melt_kwh=melt_kwh, hold_kwh=hold_kwh, tap_kwh=tap_kwh, cold_start_kwh=cold,
                furnace_kwh=melt_kwh + hold_kwh + tap_kwh,
                superheat_c=p["superheat_c"], slag_pct=p["slag_pct"], lid_open=p["lid_open"],
                efficiency=eff, reject_rate=float(np.clip(rng.normal(*K.REJECT_RATE), 0.02, 0.09)),
            ))
            clock = start + dur + K.CHARGE_GAP_MIN
    df = pd.DataFrame(rows)
    df["liquid_t"] = df.charge_kg / 1000
    df["good_t"] = df.liquid_t * K.YIELD * (1 - df.reject_rate)
    df["sec_liquid"] = df.furnace_kwh / df.liquid_t
    df["melt_sec"] = (df.melt_kwh - df.cold_start_kwh) / df.liquid_t
    df["first_heat"] = (df.heat_no == 1).astype(int)
    return df


# ---------------------------------------------------------------- time series
def render_timeseries(heats, rng, days=None):
    """Render 10-second power channels (kW). Returns (DataFrame, list of auxiliary load names)."""
    days = days or K.DAYS
    spd = 86400 // K.DT_S
    N = days * spd
    t_min = (np.arange(N) % spd) * K.DT_S / 60.0
    day_idx = np.arange(N) // spd + 1
    names = ["furnace", "compressor", "cooling_pump", "fume_extraction", "sand_mixer", "shot_blast", "grinders", "lighting_office"]
    ch = {k: np.zeros(N) for k in names}
    furnace_on = np.zeros(N, bool)
    melting = np.zeros(N, bool)
    for r in heats[heats.day <= days].itertuples():
        base = (r.day - 1) * spd
        end_day = base + spd
        def idx(m):
            return min(base + int(round(m * 60 / K.DT_S)), end_day)
        a, b = idx(r.start_min), idx(r.start_min + r.melt_min)
        c, d = idx(r.start_min + r.melt_min + r.hold_min), idx(r.end_min)
        if a >= end_day or b <= a:
            continue
        seg = K.RATED_KW * (1 + 0.01 * rng.standard_normal(b - a))
        ramp = min(12, b - a)
        seg[:ramp] *= np.linspace(0.6, 1, ramp)
        seg *= r.melt_kwh / max(1e-9, seg.sum() * K.DT_S / 3600)
        ch["furnace"][a:b] = seg
        ch["furnace"][b:c] = K.HOLD_KW * (1 + 0.03 * rng.standard_normal(c - b))
        ch["furnace"][c:d] = K.TAP_KW
        furnace_on[a:d] = True
        melting[a:b] = True
    lag = int(20 * 60 / K.DT_S)
    on = furnace_on.copy()
    for e in np.flatnonzero(np.diff(furnace_on.astype(int)) == -1):
        on[e:e + lag] = True
    ch["cooling_pump"] = on * K.AUX["cooling_pump"] * (1 + 0.02 * rng.standard_normal(N))
    ch["fume_extraction"] = melting * K.AUX["fume_extraction"] * (1 + 0.02 * rng.standard_normal(N))
    hour = t_min / 60
    for day in range(1, days + 1):
        base = (day - 1) * spd
        m = 8 * 60 + rng.uniform(0, 10)
        while m < 16.5 * 60:
            run = rng.uniform(3, 5)
            a = base + int(m * 60 / K.DT_S); b = base + int((m + run) * 60 / K.DT_S)
            ch["sand_mixer"][a:b] = K.AUX["sand_mixer"]
            m += run + rng.uniform(5, 9)
        for lo, hi in ((10, 13), (14, 18)):
            st = rng.uniform(lo, hi - 1.5) * 60
            run = rng.uniform(50, 90)
            a = base + int(st * 60 / K.DT_S); b = base + int((st + run) * 60 / K.DT_S)
            ch["shot_blast"][a:b] = K.AUX["shot_blast"]
        for _ in range(3):
            m = 9 * 60 + rng.uniform(0, 30)
            while m < 18 * 60:
                run = rng.uniform(2, 10)
                a = base + int(m * 60 / K.DT_S); b = base + int((m + run) * 60 / K.DT_S)
                ch["grinders"][a:b] += K.AUX["grinders"]
                m += run + rng.uniform(3, 15)
        fixed = day >= K.COMPRESSOR_FIX_DAY
        leak = K.COMPRESSOR_LEAK_AFTER if fixed else K.COMPRESSOR_LEAK_BEFORE
        h = hour[base:base + spd]
        demand = np.where((h >= 8) & (h < 18), 0.45, 0.05) + leak
        running = np.ones(spd, bool) if not fixed else ((h >= K.CREW_WINDOW[0]) & (h < K.CREW_WINDOW[1] + 1))
        phase = (np.arange(spd) * K.DT_S) % 120 / 120.0
        loaded = phase < np.clip(demand, 0, 1)
        ch["compressor"][base:base + spd] = np.where(loaded, K.COMPRESSOR_LOAD_KW, K.COMPRESSOR_UNLOAD_KW) * running
    ch["shot_blast"] *= (1 + 0.03 * rng.standard_normal(N)) * (ch["shot_blast"] > 0)
    ch["grinders"] *= (1 + 0.05 * rng.standard_normal(N)) * (ch["grinders"] > 0)
    ch["lighting_office"] = ((hour >= 6) & (hour < 24)) * K.AUX["lighting_office"] + 0.6
    aux = ["cooling_pump", "fume_extraction", "sand_mixer", "shot_blast", "grinders", "lighting_office"]
    mains = ch["furnace"] + ch["compressor"] + sum(ch[k] for k in aux) + 0.25 * rng.standard_normal(N)
    ts = pd.DataFrame({"day": day_idx, "minute": t_min, "mains_kw": mains, "furnace_kw": ch["furnace"],
                       "compressor_kw": ch["compressor"], **{f"{k}_kw": ch[k] for k in aux}})
    ts["residual_kw"] = ts.mains_kw - ts.furnace_kw - ts.compressor_kw
    return ts, aux
