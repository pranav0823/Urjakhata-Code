"""End-to-end run: simulate 90 operating days, run every UrjaKhata engine and
export results for the website.

Usage (from the repository root):  python -m engine.pipeline
Writes: public/data/urjakhata-data.js (read by the website), public/data/results.json,
        data/heats.csv, data/daily.csv, data/nilm_eval.csv
"""
import json
import os
import time
import numpy as np
import pandas as pd
from . import config as K, sim, tod, sec, mv, carbon, tariff, robustness
from .nilm import HybridNILM, ShareBaseline, evaluate, confidence_tier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PUB = os.path.join(ROOT, "public", "data")
DT_H = K.DT_S / 3600


def improved_profile():
    pi = {k: v[0] for k, v in K.PRACTICE_IMPROVED.items()}
    melt_min, melt_kwh, hold_kwh, _, _ = sim.heat_energy(K.CHARGE_KG, pi["superheat_c"], pi["slag_pct"],
                                                         pi["lid_open"], pi["hold_min"], K.FURNACE_EFF, False)
    return tod.heat_profile(melt_kwh, melt_min, hold_kwh, pi["hold_min"])


def daily_from_ts(ts):
    hour = ts.minute.values / 60
    r = tariff.rate_array(K.BASE_STATE, hour)
    lab = np.array([tariff.window_label(K.BASE_STATE, h) for h in np.arange(0, 24, 1 / 12)])
    lab_ts = lab[(hour * 12).astype(int) % 288]
    kwh = ts.mains_kw.values * DT_H
    df = pd.DataFrame({"day": ts.day.values, "kwh": kwh, "cost": kwh * r,
                       "peak": kwh * (lab_ts == "peak"), "solar": kwh * (lab_ts == "solar"),
                       "furnace": ts.furnace_kw.values * DT_H, "comp": ts.compressor_kw.values * DT_H,
                       "night_comp": ts.compressor_kw.values * DT_H * (hour < 6),
                       "resid": ts.residual_kw.values * DT_H})
    g = df.groupby("day").sum()
    d = pd.DataFrame({"plant_kwh": g.kwh, "furnace_meter_kwh": g.furnace, "compressor_kwh": g.comp,
                      "residual_kwh": g.resid, "cost_rs": g.cost, "peak_kwh": g.peak, "solar_kwh": g.solar,
                      "night_compressor_kwh": g.night_comp})
    d["avg_rate"] = d.cost_rs / d.plant_kwh
    return d


def peak_kwh_of_plan(starts, profile, state):
    tot = 0.0
    for sh in starts:
        for i, e in enumerate(profile):
            if tariff.window_label(state, sh + (i + 0.5) * tod.SLOT_MIN / 60) == "peak":
                tot += e
    return tot


def main():
    t0 = time.time()
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(PUB, exist_ok=True)

    prof = improved_profile()
    states = tod.state_comparison(prof)
    gj_plans = {int(n): p["start_hours"] for n, p in states[K.BASE_STATE]["plans"].items()}
    plan_peak = {n: peak_kwh_of_plan(s, prof, K.BASE_STATE) for n, s in gj_plans.items()}

    # pass 1: when does the drift detector fire? pass 2: the plant acts on it (relines)
    ref_days = (K.TOD_START_DAY, K.LINING_WEAR_START_DAY - 1)
    heats_nofix = sim.plan_heats(np.random.default_rng(K.SEED), None, gj_plans)
    alert, _, _, _ = sec.cusum_drift(heats_nofix, ref_days)
    reline_day = alert["day"] + K.RELINE_LAG_DAYS if alert else None
    heats = sim.plan_heats(np.random.default_rng(K.SEED), reline_day, gj_plans)
    _, trace, resid, drift_model = sec.cusum_drift(heats, ref_days)
    heats["cusum"] = trace
    heats["drift_resid"] = resid
    avoided_kwh = float(heats_nofix.furnace_kwh.sum() - heats.furnace_kwh.sum())

    ts, loads = sim.render_timeseries(heats, np.random.default_rng(K.SEED + 1))
    daily_ts = daily_from_ts(ts)

    # NILM: learn on commissioning days 1-4 (portable clamp labels). When the melt schedule
    # changes (Time-of-Day plan from day 43) the clamps go back on for one day and the model is refreshed.
    in_train = ts.day.between(*K.NILM_TRAIN_DAYS)
    model, naive = HybridNILM(loads).fit(ts[in_train]), ShareBaseline(loads).fit(ts[in_train])
    in_train_r = in_train | (ts.day == K.NILM_RELABEL_DAY)
    model_r, naive_r = HybridNILM(loads).fit(ts[in_train_r]), ShareBaseline(loads).fit(ts[in_train_r])
    tests = {}
    for name, days, m, nv in [("days_5_7", (5, 7), model, naive),
                              ("days_80_82_no_relabel", (80, 82), model, naive),
                              ("days_80_82", (80, 82), model_r, naive_r)]:
        part = ts[ts.day.between(*days)]
        ev = evaluate(part, m.predict(part), loads)
        evn = evaluate(part, nv.predict(part), loads)
        ev["naive_sae"] = evn.sae.values
        ev["naive_f1"] = evn.f1_on_off.values
        ev["naive_nde"] = evn.nde.values
        ev["tier"] = [confidence_tier(s, f) for s, f in zip(ev.sae, ev.f1_on_off)]
        tests[name] = ev
    early = ts.day < K.NILM_RELABEL_DAY
    pred_all = pd.concat([model.predict(ts[early]), model_r.predict(ts[~early])])
    nilm_daily = pred_all.groupby(ts.day.values).sum() * DT_H
    nilm_daily.columns = [f"nilm_{c}_kwh" for c in nilm_daily.columns]

    daily = sec.daily_sec(heats, daily_ts.join(nilm_daily))
    mvb, mvc = mv.option_b(heats), mv.option_c(daily)
    daily["adjusted_baseline_kwh"] = np.nan
    daily.loc[daily.day > K.BASELINE_DAYS, "adjusted_baseline_kwh"] = mvc["daily_adjusted"]

    wear = (daily.day >= K.LINING_WEAR_START_DAY) & (daily.day <= (reline_day or 0))
    base = daily[daily.day <= K.BASELINE_DAYS]
    steady = daily[(daily.day >= 40) & ~wear]

    def period(d, h):
        return dict(days=int(len(d)), liquid_t_per_day=float(d.liquid_t.mean()), good_t_per_day=float(d.good_t.mean()),
                    heats_per_day=float(d.heats.mean()),
                    sec_liquid=float(d.furnace_kwh.sum() / d.liquid_t.sum()),
                    sec_good_plant=float(d.plant_kwh.sum() / d.good_t.sum()),
                    reject_rate=float((h.reject_rate * h.liquid_t).sum() / h.liquid_t.sum()),
                    avg_rate=float(d.cost_rs.sum() / d.plant_kwh.sum()),
                    rs_per_good_t=float(d.cost_rs.sum() / d.good_t.sum()),
                    peak_share=float(d.peak_kwh.sum() / d.plant_kwh.sum()),
                    solar_share=float(d.solar_kwh.sum() / d.plant_kwh.sum()),
                    compressor_kwh_per_day=float(d.compressor_kwh.mean()),
                    furnace_kwh_per_day=float(d.furnace_kwh.mean()),
                    hold_min=float(h.hold_min.mean()), superheat_c=float(h.superheat_c.mean()),
                    slag_pct=float(h.slag_pct.mean()), lid_open=float(h.lid_open.mean()))
    hb = heats[heats.day <= K.BASELINE_DAYS]
    hs = heats[heats.day.isin(steady.day)]
    P0, P1 = period(base, hb), period(steady, hs)

    annual_liquid = K.ANNUAL_LIQUID_TONNES
    annual_good = annual_liquid * K.YIELD * (1 - P0["reject_rate"])
    kwh_saved = (P0["sec_good_plant"] - P1["sec_good_plant"]) * annual_good
    rs_saved = (P0["rs_per_good_t"] - P1["rs_per_good_t"]) * annual_good
    rs_energy = kwh_saved * P0["avg_rate"]
    furnace_kwh_saved = (P0["sec_liquid"] - P1["sec_liquid"]) * annual_liquid
    comp_kwh_saved = (P0["compressor_kwh_per_day"] - P1["compressor_kwh_per_day"]) * K.OPERATING_DAYS_PER_YEAR
    kit_low = sum(b[1] for b in K.BOM); kit_high = sum(b[2] for b in K.BOM)
    yr1_low = kit_low + 12 * K.SUBSCRIPTION_RS_MONTH[0]
    yr1_high = kit_high + 12 * K.SUBSCRIPTION_RS_MONTH[1]
    headline = dict(
        baseline=P0, steady_state=P1,
        sec_liquid_reduction_pct=100 * (1 - P1["sec_liquid"] / P0["sec_liquid"]),
        sec_good_plant_reduction_pct=100 * (1 - P1["sec_good_plant"] / P0["sec_good_plant"]),
        annual_liquid_t=annual_liquid, annual_good_t=annual_good,
        annual_kwh_saved=kwh_saved, annual_mwh_saved=kwh_saved / 1000,
        annual_furnace_kwh_saved=furnace_kwh_saved, annual_compressor_kwh_saved=comp_kwh_saved,
        annual_rs_saved=rs_saved, annual_rs_from_energy=rs_energy, annual_rs_from_tod=rs_saved - rs_energy,
        annual_tco2_reporting=kwh_saved / 1000 * K.GRID_EF_REPORTING,
        annual_tco2_ccts=kwh_saved / 1000 * K.GRID_EF_CCTS,
        throughput_change_pct=100 * (P1["liquid_t_per_day"] / P0["liquid_t_per_day"] - 1),
        reject_rate_change_pts=100 * (P1["reject_rate"] - P0["reject_rate"]),
        drift_alert=alert, reline_day=reline_day, drift_model=drift_model,
        drift_heats_after_onset=int(((heats.day >= K.LINING_WEAR_START_DAY) &
                                     (heats.heat_id <= alert["heat_id"])).sum()) if alert else None,
        drift_avoided_kwh_to_day90=avoided_kwh,
        tod_isolated_annual_rs=states[K.BASE_STATE]["annual_rs"],
        annual_rs_headline=rs_energy + states[K.BASE_STATE]["annual_rs"],
        kit_rs=[kit_low, kit_high], year1_cost_rs=[yr1_low, yr1_high],
        payback_months=[12 * yr1_low / (rs_energy + states[K.BASE_STATE]["annual_rs"]),
                        12 * yr1_high / (rs_energy + states[K.BASE_STATE]["annual_rs"])],
        payback_months_energy_only=[12 * yr1_low / rs_energy, 12 * yr1_high / rs_energy],
    )
    headline = json.loads(json.dumps(headline, default=float))

    # robustness: savings under partial adoption and parameter uncertainty; drift alarm reliability
    ref = dict(avg_rate=P0["avg_rate"], tod_rs_full=states[K.BASE_STATE]["annual_rs"],
               compressor_kwh_saved_full=comp_kwh_saved,
               aux_kwh_saved_full=kwh_saved - furnace_kwh_saved - comp_kwh_saved)
    fast = robustness.full_adoption_check()
    robust = json.loads(json.dumps(dict(
        reference=ref,
        fast_model_check=dict(fast=fast, sim=dict(sec_baseline=P0["sec_liquid"], sec_improved=P1["sec_liquid"],
                                                  furnace_kwh_saved=furnace_kwh_saved, compressor_kwh_saved=comp_kwh_saved)),
        savings=robustness.savings_monte_carlo(ref),
        adherence=robustness.adherence_curve(ref),
        drift=robustness.drift_reliability(),
        drift_sweep=robustness.threshold_sweep(),
    ), default=float))
    nilm_rob = json.loads(json.dumps(robustness.nilm_seeds(heats), default=float))

    car_base = carbon.period_figures(heats, daily, (1, K.BASELINE_DAYS))
    car_now = carbon.period_figures(heats, daily, ((reline_day or 61) + 1, K.DAYS))
    passport = carbon.passport(heats, daily, ((reline_day or 61) + 1, K.DAYS), 18.0, "EXP-2026-031")

    night = daily.set_index("day").night_compressor_kwh
    briefings = {}
    for day in range(2, K.DAYS + 1):
        y = heats[heats.day == day - 1]
        yd = daily[daily.day == day - 1].iloc[0]
        wk = daily[daily.day.between(max(1, day - 7), day - 1)]
        pp = plan_peak.get(len(y), 0.0) if day - 1 >= K.TOD_START_DAY else 0.0
        cards = sec.action_cards(y, float(night.loc[day - 1]), day - 1, pp)
        drifting = bool(alert and alert["day"] <= day - 1 < (reline_day or 999))
        if drifting:
            cards = [sec.drift_card(alert, float(yd.liquid_t))] + cards[:2]
        briefings[day] = dict(day=day, yesterday_sec_good=float(yd.sec_good_plant), yesterday_sec_liquid=float(yd.sec_liquid),
                              best_week_sec_good=float(wk.sec_good_plant.min()), yesterday_cost=float(yd.cost_rs),
                              drift=drifting,
                              cards=[{k: (round(v, 1) if isinstance(v, float) else v) for k, v in c.items()} for c in cards])

    def trace_day(day):
        part = ts[ts.day == day]
        pr = pred_all.loc[part.index]
        g = part.minute.astype(int).values
        out = {k: part[c].groupby(g).mean().round(1).tolist() for k, c in
               {"mains": "mains_kw", "furnace": "furnace_kw", "compressor": "compressor_kw"}.items()}
        out["nilm"] = {k: pr[k].groupby(g).mean().round(2).tolist() for k in loads}
        out["true"] = {k: part[f"{k}_kw"].groupby(g).mean().round(2).tolist() for k in loads}
        return out

    shifts_ok = {}
    for n, s in gj_plans.items():
        counts = [sum(1 for x in s if a <= x < b) for a, b in K.SHIFTS]
        shifts_ok[str(n)] = dict(per_shift=counts, ok=all(c <= K.MAX_HEATS_PER_SHIFT for c in counts))

    heats.to_csv(os.path.join(DATA, "heats.csv"), index=False)
    daily.round(4).to_csv(os.path.join(DATA, "daily.csv"), index=False)
    pd.concat([v.assign(test=k) for k, v in tests.items()]).to_csv(os.path.join(DATA, "nilm_eval.csv"), index=False)

    heats_out = heats.assign(start_h=heats.start_min / 60, end_h=heats.end_min / 60)[
        ["heat_id", "day", "heat_no", "start_h", "end_h", "charge_kg", "pig_iron_share", "melt_min", "hold_min",
         "furnace_kwh", "sec_liquid", "melt_sec", "superheat_c", "slag_pct", "reject_rate", "efficiency", "cusum", "drift_resid"]].round(3)
    keep_daily = ["day", "heats", "liquid_t", "good_t", "furnace_kwh", "plant_kwh", "compressor_kwh", "cost_rs",
                  "peak_kwh", "solar_kwh", "avg_rate", "sec_liquid", "sec_good_plant", "reject_rate",
                  "adjusted_baseline_kwh", "night_compressor_kwh"] + list(nilm_daily.columns)
    results = dict(
        generated=time.strftime("%Y-%m-%d"),
        config=dict(days=K.DAYS, baseline_days=K.BASELINE_DAYS, sop_start=K.SOP_START_DAY,
                    compressor_fix=K.COMPRESSOR_FIX_DAY, tod_start=K.TOD_START_DAY, wear_start=K.LINING_WEAR_START_DAY,
                    dt_s=K.DT_S, rated_kw=K.RATED_KW, charge_kg=K.CHARGE_KG, furnace_eff=K.FURNACE_EFF,
                    yield_=K.YIELD, grid_ef=K.GRID_EF_REPORTING, grid_ef_ccts=K.GRID_EF_CCTS,
                    pig_iron_ef=K.PIG_IRON_EF, lpg_kg_t=K.LPG_KG_PER_T_LIQUID, lpg_ef=K.LPG_EF_KG_CO2_PER_KG,
                    crew_window=K.CREW_WINDOW, shifts=K.SHIFTS, max_heats_per_shift=K.MAX_HEATS_PER_SHIFT,
                    baseline_first_heat=K.BASELINE_FIRST_HEAT_H, base_state=K.BASE_STATE,
                    operating_days=K.OPERATING_DAYS_PER_YEAR, cusum_k=K.CUSUM_K, cusum_h=K.CUSUM_H,
                    nilm_relabel_day=K.NILM_RELABEL_DAY),
        headline=headline, robustness=robust, mv=dict(option_b=mvb, option_c={k: v for k, v in mvc.items() if k != "daily_adjusted"}),
        nilm=dict(loads=loads, train_days=list(K.NILM_TRAIN_DAYS), relabel_day=K.NILM_RELABEL_DAY, seeds=nilm_rob, tests={k: v.round(4).to_dict("records") for k, v in tests.items()}),
        tariffs={s: tariff.summary(s) for s in K.TARIFFS},
        tod=dict(states=states, profile_kwh=prof.round(2).tolist(), shifts_check=shifts_ok, plan_peak_kwh=plan_peak),
        carbon=dict(baseline=car_base, current=car_now, passport=passport),
        bom=[dict(item=a, low=b, high=c, basis=d) for a, b, c, d in K.BOM],
        params=K.PARAMS,
        daily=daily[keep_daily].round(3).replace({np.nan: None}).to_dict("records"),
        heats=heats_out.to_dict("records"),
        briefings=briefings,
        traces={k: dict(day=v, **trace_day(v)) for k, v in {"baseline": 12, "improved": 85}.items()},
    )
    with open(os.path.join(PUB, "results.json"), "w") as f:
        json.dump(results, f, default=float, separators=(",", ":"))
    with open(os.path.join(PUB, "urjakhata-data.js"), "w") as f:
        f.write("/* Generated by python -m engine.pipeline. Do not edit by hand. */\nwindow.URJA = ")
        json.dump(results, f, default=float, separators=(",", ":"))
        f.write(";\n")
    print(f"done in {time.time() - t0:.0f}s")
    return results


if __name__ == "__main__":
    r = main()
    h = r["headline"]
    print(json.dumps({k: v for k, v in h.items() if k not in ("baseline", "steady_state")}, indent=1))
    print("baseline", json.dumps(h["baseline"]))
    print("steady  ", json.dumps(h["steady_state"]))
    for k in ("option_b", "option_c"):
        print(k, json.dumps(r["mv"][k]))
    for k, v in r["nilm"]["tests"].items():
        print(k); print(pd.DataFrame(v)[["load", "sae", "nde", "f1_on_off", "naive_sae", "naive_f1", "tier"]].round(3).to_string())
    print("carbon base", r["carbon"]["baseline"]); print("carbon now", r["carbon"]["current"])
    print({s: round(v["annual_rs"]) for s, v in r["tod"]["states"].items()}, r["tod"]["shifts_check"])
    rb = r["robustness"]
    print("savings MC", json.dumps(rb["savings"]["percentiles"]), "stress", rb["savings"]["stress_case"]["rs"], rb["savings"]["stress_case"]["payback_months"])
    print("drift", json.dumps(rb["drift"]["scenarios"]))
    print("sweep", json.dumps(rb["drift_sweep"]))
