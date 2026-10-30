"""Time-of-Day melt scheduler.

Mixed-integer program solved with SciPy's HiGHS solver. Decision: which
5-minute slots each heat starts in. Constraints:
  * exactly n heats in the day (the day's output is unchanged)
  * one furnace: heats never overlap (each heat includes tapping and recharging)
  * every heat starts and finishes inside the crew window (moulding line staffed)
  * at most MAX_HEATS_PER_SHIFT heats start in each shift
Objective: lowest furnace electricity cost on the state's effective ToD rate.
"""
import math
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from . import config as K
from .tariff import rate

SLOT_MIN = 5
SLOTS = 24 * 60 // SLOT_MIN


def heat_profile(melt_kwh, melt_min, hold_kwh, hold_min):
    """kWh drawn in each 5-minute slot of one heat cycle (melt, hold, tap, recharge)."""
    total = melt_min + hold_min + K.TAP_MIN + K.CHARGE_GAP_MIN
    n = math.ceil(total / SLOT_MIN)
    prof = np.zeros(n)
    tap_kwh = K.TAP_KW * K.TAP_MIN / 60
    for i in range(n):
        a, b = i * SLOT_MIN, (i + 1) * SLOT_MIN
        prof[i] += melt_kwh * max(0, min(b, melt_min) - a) / melt_min
        prof[i] += hold_kwh * max(0, min(b, melt_min + hold_min) - max(a, melt_min)) / max(hold_min, 1e-9)
        t0, t1 = melt_min + hold_min, melt_min + hold_min + K.TAP_MIN
        prof[i] += tap_kwh * max(0, min(b, t1) - max(a, t0)) / K.TAP_MIN
    return prof


def _slot_rates(state):
    return np.array([rate(state, ((s % SLOTS) + 0.5) * SLOT_MIN / 60) for s in range(2 * SLOTS)])


def optimise_day(n_heats, profile, state=K.BASE_STATE):
    D = len(profile)
    first = K.CREW_WINDOW[0] * 60 // SLOT_MIN
    last_start = K.CREW_WINDOW[1] * 60 // SLOT_MIN - D
    starts = np.arange(first, last_start + 1)
    r = _slot_rates(state)
    cost = np.array([(profile * r[s:s + D]).sum() for s in starts])
    rows, lb, ub = [np.ones(len(starts))], [n_heats], [n_heats]
    for t in range(SLOTS):                      # no overlap on the single furnace
        row = ((starts <= t) & (t < starts + D)).astype(float)
        if row.sum() > 1:
            rows.append(row); lb.append(0); ub.append(1)
    for a, b in K.SHIFTS:                       # crew limit per shift
        row = ((starts * SLOT_MIN / 60 >= a) & (starts * SLOT_MIN / 60 < b)).astype(float)
        rows.append(row); lb.append(0); ub.append(K.MAX_HEATS_PER_SHIFT)
    res = milp(c=cost, constraints=LinearConstraint(np.array(rows), lb, ub),
               integrality=np.ones(len(starts)), bounds=Bounds(0, 1))
    if res.x is None:
        return dict(status=res.message, feasible=False)
    chosen = sorted(starts[np.round(res.x).astype(bool)])
    return dict(status=res.message, feasible=True, start_hours=[float(s * SLOT_MIN / 60) for s in chosen],
                plan_cost_rs=float(res.fun), heat_minutes=D * SLOT_MIN, slot_minutes=SLOT_MIN)


def habitual_cost(n_heats, profile, state=K.BASE_STATE, first_h=K.BASELINE_FIRST_HEAT_H):
    D = len(profile)
    s0 = int(first_h * 60 // SLOT_MIN)
    r = _slot_rates(state)
    return float(sum((profile * r[s0 + i * D: s0 + (i + 1) * D]).sum() for i in range(n_heats)))


def state_comparison(profile):
    """Annual furnace-cost saving from the optimised plan versus the habitual schedule, per state."""
    out = {}
    for st in K.TARIFFS:
        days = []
        for n in K.HEATS_PER_DAY:
            plan = optimise_day(n, profile, st)
            hab = habitual_cost(n, profile, st)
            days.append(dict(n=n, plan=plan, habitual_cost=hab, saving=hab - plan["plan_cost_rs"]))
        avg = float(np.mean([d["saving"] for d in days]))
        out[st] = dict(per_day_rs=avg, annual_rs=avg * K.OPERATING_DAYS_PER_YEAR,
                       plans={str(d["n"]): dict(start_hours=d["plan"]["start_hours"], plan_cost_rs=d["plan"]["plan_cost_rs"],
                                                habitual_cost_rs=d["habitual_cost"]) for d in days},
                       heat_minutes=days[0]["plan"]["heat_minutes"])
    return out
