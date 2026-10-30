"""Test the machine split on real factory data: IMDELD.

IMDELD (Industrial Machines Dataset for Electrical Load Disaggregation) was recorded
at 1 Hz in a Brazilian poultry-feed factory and is published on IEEE DataPort. The raw
files are not redistributed here: download them, then run

    python -m engine.realdata /path/to/imdeld/csvs

It converts each CSV to 10-second mean active power (cached in data/imdeld_10s/, not
committed), runs three tests with the same HybridNILM model and protocol as the
simulation (learn from 4 labelled days, test on later unseen days, week by week,
against the simple fixed-share split), and writes public/data/realdata.js.

Tests:
  A. UrjaKhata design. Pelletizer sub-circuit: both pelletizers (about 90% of the
     energy) are metered, like the furnace and compressor. The model splits the
     leftover into exhaust fan II and double-pole contactor II. Exhaust fan I and
     contactor I are also in the leftover but not labelled, as in a real plant where
     not every machine is clamped.
  B. Same sub-circuit with nothing metered: the model must split all four machines.
     Shows what metering the big loads is worth.
  C. Milling sub-circuit, nothing metered: two near-identical milling machines.
"""
import json
import os
import sys
import time
import numpy as np
import pandas as pd
from .nilm import HybridNILM, ShareBaseline, evaluate, confidence_tier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "imdeld_10s")
PUB = os.path.join(ROOT, "public", "data")
TZ = "America/Sao_Paulo"
TRAIN_DAYS = 4
STEP = "10s"
PER_DAY = 8640
MIN_COVER = 0.95

NAMES = {"pelletizer-I": "Pelletizer I", "pelletizer-II": "Pelletizer II", "exhaustfan-II": "Exhaust fan II",
         "doublepolecontactor-II": "Double-pole contactor II", "millingmachine-I": "Milling machine I",
         "millingmachine-II": "Milling machine II"}


def convert(csv_dir):
    """1 Hz CSV to 10-second mean kW, cached as pickles."""
    os.makedirs(CACHE, exist_ok=True)
    for f in sorted(os.listdir(csv_dir)):
        if not f.endswith(".csv"):
            continue
        out = os.path.join(CACHE, f.replace(".csv", ".pkl"))
        if os.path.exists(out):
            continue
        t0 = time.time()
        try:
            df = pd.read_csv(os.path.join(csv_dir, f), usecols=["timestamp", "active_power"], engine="pyarrow",
                             dtype={"timestamp": "string"})
        except ImportError:
            df = pd.read_csv(os.path.join(csv_dir, f), usecols=["timestamp", "active_power"], dtype={"timestamp": str})
        ts = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S%z", utc=True)
        p = pd.Series(pd.to_numeric(df["active_power"], errors="coerce").values / 1000.0, index=ts).sort_index()
        p = p[~p.index.duplicated()]
        r = p.resample(STEP).agg(["mean", "count"])
        r.columns = ["kw", "n"]
        r.to_pickle(out)
        print(f"converted {f}: {len(df):,} rows in {time.time() - t0:.0f}s", flush=True)


def frame(names):
    """Aligned 10 s frame for the given channels: complete local days only (>= 95% of steps
    present in every channel), short gaps (up to 1 minute) interpolated."""
    ch = {n: pd.read_pickle(os.path.join(CACHE, f"{n}.pkl")) for n in names}
    df = pd.concat({n: c.kw.where(c.n >= 5) for n, c in ch.items()}, axis=1)
    df.index = df.index.tz_convert(TZ)
    days = []
    for day, g in df.groupby(df.index.date):
        grid = pd.date_range(pd.Timestamp(day).tz_localize(TZ), periods=PER_DAY, freq=STEP)
        g = g.reindex(grid)
        if g.notna().all(axis=1).mean() < MIN_COVER:
            continue
        g = g.interpolate(limit=6, limit_direction="both")
        if g.isna().any().any():
            continue
        days.append(g)
    out = pd.concat(days)
    out["day"] = pd.factorize(out.index.date)[0] + 1
    out["minute"] = out.index.hour * 60 + out.index.minute + out.index.second / 60
    return out


def _ts(df, mains, metered, loads):
    ts = pd.DataFrame({"day": df.day.values, "minute": df.minute.values}, index=df.index)
    ts["furnace_kw"] = df[metered].sum(axis=1).values if metered else 0.0
    ts["residual_kw"] = (df[mains] - (df[metered].sum(axis=1) if metered else 0.0)).values
    for k in loads:
        ts[f"{k}_kw"] = df[k].values
    return ts


def run_test(name, mains, metered, loads, title, note, other_bucket=True, verbose=True):
    """other_bucket: model the unlabelled remainder of the leftover load as its own output, so
    the energy-balance step does not push unlabelled machines' energy onto labelled ones."""
    df = frame([mains] + metered + loads)
    ts = _ts(df, mains, metered, loads)
    ts["other_kw"] = ts.residual_kw - ts[[f"{k}_kw" for k in loads]].sum(axis=1)
    fit_loads = loads + (["other"] if other_bucket else [])
    train = ts[ts.day <= TRAIN_DAYS]
    on_kw = {k: max(0.1, 0.2 * float(train[f"{k}_kw"].quantile(0.95))) for k in loads}
    if metered:
        p99 = float(train.furnace_kw.quantile(0.99))
        model = HybridNILM(fit_loads, on_kw=0.1 * p99, hi_kw=0.6 * p99, use_metered=True)
    else:
        model = HybridNILM(fit_loads, use_metered=False)
    model.fit(train)
    naive = ShareBaseline(loads).fit(train)
    test = ts[ts.day > TRAIN_DAYS]
    pred, predn = model.predict(test)[loads], naive.predict(test)
    # week-by-week blocks of unseen days
    blocks, rows = [], []
    last = int(test.day.max())
    for a in range(TRAIN_DAYS + 1, last + 1, 7):
        b = min(a + 6, last)
        m = test.day.between(a, b).values
        if m.sum() < 3 * PER_DAY:
            continue
        ev = evaluate(test[m], pred[m], loads, on_kw)
        evn = evaluate(test[m], predn[m], loads, on_kw)
        blocks.append(dict(days=[a, b]))
        for i, k in enumerate(loads):
            rows.append(dict(block=len(blocks) - 1, load=k, sae=float(ev.sae.iloc[i]), f1=float(ev.f1_on_off.iloc[i]),
                             nde=float(ev.nde.iloc[i]), naive_sae=float(evn.sae.iloc[i]), naive_f1=float(evn.f1_on_off.iloc[i]),
                             share_true=float(ev.share_true.iloc[i])))
    ev_all, evn_all = evaluate(test, pred, loads, on_kw), evaluate(test, predn, loads, on_kw)
    total = float(ts[ts.day > TRAIN_DAYS].residual_kw.clip(lower=0).sum())
    per_load = []
    for i, k in enumerate(loads):
        r = [x for x in rows if x["load"] == k]
        per_load.append(dict(
            load=k, name=NAMES.get(k, k), on_kw=on_kw[k],
            energy_share=float(test[f"{k}_kw"].sum() / max(total, 1e-9)),
            sae_all=float(ev_all.sae.iloc[i]), naive_sae_all=float(evn_all.sae.iloc[i]),
            f1_all=float(ev_all.f1_on_off.iloc[i]), naive_f1_all=float(evn_all.f1_on_off.iloc[i]),
            sae_week_median=float(np.median([x["sae"] for x in r])), sae_week_worst=float(max(x["sae"] for x in r)),
            naive_sae_week_median=float(np.median([x["naive_sae"] for x in r])),
            naive_sae_week_worst=float(max(x["naive_sae"] for x in r)),
            tier=confidence_tier(float(np.median([x["sae"] for x in r])), float(ev_all.f1_on_off.iloc[i]))))
    wsae = lambda key: float(sum(p[key] * p["energy_share"] for p in per_load) / sum(p["energy_share"] for p in per_load))
    res = dict(name=name, title=title, note=note, mains=mains, metered=metered, loads=loads, other_bucket=other_bucket,
               unlabelled_share=float(test.other_kw.clip(lower=0).sum() / max(total, 1e-9)),
               metered_share=float(df[metered].sum(axis=1).sum() / df[mains].clip(lower=0).sum()) if metered else 0.0,
               train_days=TRAIN_DAYS, test_days=int(last - TRAIN_DAYS), total_days=int(last),
               first_day=str(df.index[0].date()), last_day=str(df.index[-1].date()),
               weeks=len(blocks), per_load=per_load,
               weighted_sae_week_median=wsae("sae_week_median"), weighted_naive_sae_week_median=wsae("naive_sae_week_median"),
               mean_f1=float(np.mean([p["f1_all"] for p in per_load])), mean_naive_f1=float(np.mean([p["naive_f1_all"] for p in per_load])),
               weekly=rows, blocks=blocks)
    if not verbose:
        return res
    print(f"{name}{'' if other_bucket else ' (no other bucket)'}: {res['total_days']} days, {res['weeks']} test weeks, weighted SAE {res['weighted_sae_week_median']:.3f} "
          f"(naive {res['weighted_naive_sae_week_median']:.3f}), F1 {res['mean_f1']:.2f} (naive {res['mean_naive_f1']:.2f})", flush=True)
    for p in per_load:
        print(f"   {p['name']:<26} share {p['energy_share']:.3f} SAE wk med {p['sae_week_median']:.3f} worst {p['sae_week_worst']:.3f} "
              f"| naive {p['naive_sae_week_median']:.3f} | F1 {p['f1_all']:.2f} naive {p['naive_f1_all']:.2f} | {p['tier']}", flush=True)
    return res


TESTS = [
    ("A_hybrid", "pelletizer-subcircuit", ["pelletizer-I", "pelletizer-II"], ["exhaustfan-II", "doublepolecontactor-II"],
     "UrjaKhata design: big loads metered, leftover split",
     "Both pelletizers metered (like the furnace and compressor). Exhaust fan I and contactor I stay in the leftover unlabelled."),
    ("B_unmetered", "pelletizer-subcircuit", [], ["pelletizer-I", "pelletizer-II", "exhaustfan-II", "doublepolecontactor-II"],
     "Same circuit, nothing metered",
     "The model must split all four machines from the sub-circuit meter alone."),
    ("C_milling", "millingmachine-subcircuit", [], ["millingmachine-I", "millingmachine-II"],
     "Two near-identical milling machines, nothing metered",
     "The hardest case: two machines of the same type and size on one meter."),
]


def main(csv_dir=None):
    t0 = time.time()
    if csv_dir:
        convert(csv_dir)
    out = dict(dataset="IMDELD: Industrial Machines Dataset for Electrical Load Disaggregation",
               source="IEEE DataPort; a poultry-feed factory in Brazil, 1 Hz, Oct 2017 to Apr 2018",
               resolution_s=10, train_days=TRAIN_DAYS, tests=[run_test(*t) for t in TESTS],
               first_run=[{k: v for k, v in run_test(*t, other_bucket=False).items() if k not in ("weekly", "blocks")} for t in TESTS],
               generated=time.strftime("%Y-%m-%d"))
    os.makedirs(PUB, exist_ok=True)
    with open(os.path.join(PUB, "realdata.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    with open(os.path.join(PUB, "realdata.js"), "w") as f:
        f.write("/* Generated by python -m engine.realdata (IMDELD real factory data). Do not edit by hand. */\nwindow.URJA_REAL = ")
        json.dump(out, f, separators=(",", ":"))
        f.write(";\n")
    print(f"done in {time.time() - t0:.0f}s")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
