"""Effective variable electricity rate by state and hour of day.

Gujarat: (energy + ToU adder + FPPAS) x (1 + variable FPPAS) x (1 + duty)
Others:  energy x (1 + ToU %) x (1 + duty)
Demand charges are monthly and fixed for a given contract demand, so they do not
change with melt timing and are left out of the per-kWh rate.
"""
import numpy as np
from . import config as K


def rate(state, hour):
    t = K.TARIFFS[state]
    h = hour % 24
    adder_abs, adder_pct = 0.0, 0.0
    for a, b, v, kind, _ in t["windows"]:
        if a <= h < b:
            if kind == "abs":
                adder_abs += v
            else:
                adder_pct += v
    base = (t["energy"] * (1 + adder_pct) + adder_abs + t["fuel"]) * (1 + t["fuel_var"])
    return base * (1 + t["duty"])


def rate_array(state, hours):
    hours = np.asarray(hours, float) % 24
    out = np.empty(hours.shape)
    # vectorise over the 288 five-minute slots of a day
    grid = np.array([rate(state, s / 12) for s in range(288)])
    out[:] = grid[(hours * 12).astype(int) % 288]
    return out


def window_label(state, hour):
    for a, b, _, _, label in K.TARIFFS[state]["windows"]:
        if a <= hour % 24 < b:
            return label
    return "normal"


def summary(state):
    t = K.TARIFFS[state]
    hours = np.arange(0, 24, 0.5)
    r = np.array([rate(state, h) for h in hours])
    return dict(state=state, name=t["name"], short=t["short"], normal=float(rate(state, 3.0) if state != "TN" else rate(state, 12.0)),
                min=float(r.min()), max=float(r.max()), spread=float(r.max() - r.min()),
                bands=[dict(start=a, end=b, label=lab, rate=float(rate(state, (a + b) / 2))) for a, b, _, _, lab in t["windows"]],
                hourly=[round(float(rate(state, h + 0.01)), 3) for h in range(24)],
                source=t["source"], confidence=t["confidence"], demand=t["demand"])
