"""Specific energy consumption (SEC), drift detection and rupee-valued action cards."""
import numpy as np
from . import config as K
from .tariff import rate

NORMAL_RATE = rate(K.BASE_STATE, 3.0)
PEAK_RATE = rate(K.BASE_STATE, 19.0)
SOLAR_RATE = rate(K.BASE_STATE, 13.0)

# Variables the plant actually logs per heat (pyrometer, slag estimate, charge weight).
DRIFT_X = ["superheat_c", "slag_pct", "charge_kg"]


def daily_sec(heats, ts_daily):
    g = heats.groupby("day").agg(heats=("heat_id", "count"), liquid_t=("liquid_t", "sum"), good_t=("good_t", "sum"),
                                 furnace_kwh=("furnace_kwh", "sum"), reject_rate=("reject_rate", "mean"),
                                 hold_min=("hold_min", "mean"), superheat_c=("superheat_c", "mean"),
                                 slag_pct=("slag_pct", "mean"), pig_iron_share=("pig_iron_share", "mean"))
    g = g.join(ts_daily)
    g["sec_liquid"] = g.furnace_kwh / g.liquid_t
    g["sec_good_plant"] = g.plant_kwh / g.good_t
    return g.reset_index()


def _fit(df):
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in DRIFT_X])
    beta, *_ = np.linalg.lstsq(X, df.melt_sec.values, rcond=None)
    return beta


def _pred(beta, df):
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in DRIFT_X])
    return X @ beta


def cusum_drift(heats, ref_days, k_sigma=K.CUSUM_K, h_sigma=K.CUSUM_H):
    """One-sided CUSUM on the residuals of a regression of melting kWh/t on the logged
    process variables. A rise that the logged practice does not explain points to the
    equipment (lining or coil wear), not the operators."""
    ref = heats[heats.day.between(*ref_days)]
    beta = _fit(ref)
    resid_ref = ref.melt_sec.values - _pred(beta, ref)
    sd = resid_ref.std(ddof=len(DRIFT_X) + 1)
    resid = heats.melt_sec.values - _pred(beta, heats)
    s, trace, alert = 0.0, [], None
    for i, r in enumerate(heats.itertuples()):
        if r.day <= ref_days[1]:
            trace.append(0.0)
            continue
        s = max(0.0, s + resid[i] / sd - k_sigma)
        trace.append(s)
        if alert is None and s > h_sigma:
            day_mask = (heats.day == r.day).values
            alert = dict(heat_id=r.heat_id, day=int(r.day), resid_sd=float(sd),
                         ref_mean=float(ref.melt_sec.mean()),
                         recent_mean=float(heats[day_mask].melt_sec.mean()),
                         unexplained_kwh_t=float(resid[day_mask].mean()))
    model = dict(terms=["intercept"] + DRIFT_X, beta=[float(b) for b in beta], resid_sd=float(sd))
    return alert, np.array(trace), resid, model


def _n(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def drift_card(alert, liquid_t_day):
    extra = alert["unexplained_kwh_t"]
    kwh = extra * liquid_t_day
    return dict(kind="drift", rs_week=kwh * NORMAL_RATE * 6, kwh_day=kwh,
                text=f"Melting uses {extra:.0f} kWh/t more than your logged practice explains. Likely lining or coil wear: inspect the refractory lining.",
                hi=f"पिघलाई में आपकी लॉग की गई प्रैक्टिस से {extra:.0f} kWh प्रति टन ज़्यादा लग रहा है। लाइनिंग या कॉइल घिसी हो सकती है: रिफ्रैक्टरी लाइनिंग जाँचें।")


def action_cards(day_heats, night_compressor_kwh, day, plan_peak_kwh=0.0):
    """Top three actions for one day, valued in rupees per week (6 operating days)."""
    cards = []
    long_hold = day_heats[day_heats.hold_min > 12]
    if len(long_hold):
        kwh = ((long_hold.hold_min - 8) * K.HOLD_KW / 60).sum()
        worst = long_hold.sort_values("hold_min").iloc[-1]
        cards.append(dict(kind="holding", rs_week=kwh * NORMAL_RATE * 6, kwh_day=kwh,
                          text=f"Heat {int(worst.heat_no)} held {worst.hold_min:.0f} min after melt-down. Tap within 8 minutes.",
                          hi=f"हीट {int(worst.heat_no)} पिघलने के बाद {worst.hold_min:.0f} मिनट रुकी। 8 मिनट के अंदर टैप करें।"))
    sh = day_heats[day_heats.superheat_c > 20]
    if len(sh):
        kwh = ((sh.superheat_c - 12) * K.SUPERHEAT_KWH_T_PER_C * sh.liquid_t).sum()
        cards.append(dict(kind="superheat", rs_week=kwh * NORMAL_RATE * 6, kwh_day=kwh,
                          text=f"{_n(len(sh), 'heat')} tapped more than 20 C above target. Check the pyrometer before tapping.",
                          hi=f"{len(sh)} हीट लक्ष्य से 20 डिग्री से ज़्यादा गरम टैप हुईं। टैप से पहले पायरोमीटर देखें।"))
    sl = day_heats[day_heats.slag_pct > 2.8]
    if len(sl):
        kwh = ((sl.slag_pct - 2.3) * K.SLAG_KWH_T_PER_PCT * sl.liquid_t).sum()
        cards.append(dict(kind="slag", rs_week=kwh * NORMAL_RATE * 6, kwh_day=kwh,
                          text=f"Slag above 2.8% on {_n(len(sl), 'heat')}. Use cleaner, rust-free scrap in the charge.",
                          hi=f"{len(sl)} हीट में स्लैग 2.8% से ज़्यादा। साफ़, बिना जंग वाला स्क्रैप डालें।"))
    peak_kwh = 0.0
    for r in day_heats.itertuples():
        for a, b, _, _, lab in K.TARIFFS[K.BASE_STATE]["windows"]:
            if lab != "peak":
                continue
            ov = max(0.0, min(r.end_min / 60, b) - max(r.start_min / 60, a))
            peak_kwh += r.furnace_kwh * ov / ((r.end_min - r.start_min) / 60)
    extra_peak = peak_kwh - plan_peak_kwh
    if extra_peak > 50:
        cards.append(dict(kind="tod", rs_week=extra_peak * (PEAK_RATE - SOLAR_RATE) * 6, kwh_day=0.0,
                          text=f"{extra_peak:.0f} kWh of melting ran in peak hours (7 to 11 am, 6 to 10 pm) beyond the plan. Follow the melt plan that uses 11 am to 5 pm solar hours.",
                          hi=f"{extra_peak:.0f} kWh पिघलाई पीक समय (सुबह 7 से 11, शाम 6 से 10) में प्लान से ज़्यादा हुई। सुबह 11 से शाम 5 के सोलर समय वाला प्लान अपनाएँ।"))
    if night_compressor_kwh > 20:
        cards.append(dict(kind="compressor", rs_week=night_compressor_kwh * 0.7 * NORMAL_RATE * 6, kwh_day=night_compressor_kwh * 0.7,
                          text=f"Compressor used {night_compressor_kwh:.0f} kWh between midnight and 6 am with no production. Fit a timer and fix air leaks.",
                          hi=f"रात 12 से सुबह 6 के बीच कंप्रेसर ने {night_compressor_kwh:.0f} kWh खर्च किए। टाइमर लगाएँ और हवा का रिसाव ठीक करें।"))
    return sorted(cards, key=lambda c: -c["rs_week"])[:3]
