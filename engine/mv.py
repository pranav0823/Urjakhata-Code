"""Measurement and verification following IPMVP.

Option B (headline): retrofit isolation on the furnace sub-meter, per-heat regression
on charge weight and cold start. Option C (indicative): whole facility, daily regression
on liquid tonnes. Savings uncertainty follows ASHRAE Guideline 14 (fractional savings
uncertainty at 90% confidence), so every savings number carries a band.
"""
import numpy as np
from . import config as K


def _ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    p = X1.shape[1]
    dof = max(len(y) - p, 1)
    rmse = float(np.sqrt((resid ** 2).sum() / dof))
    return beta, rmse, p


def _fsu(cv, n, m, F, t=1.645):
    """ASHRAE Guideline 14 fractional savings uncertainty (no autocorrelation)."""
    # dE/E = t x 1.26 x CV x sqrt[(n/n') x (1 + 2/n) x (1/m)] / F, with n' = n
    return t * 1.26 * cv * np.sqrt((1 + 2 / n) / m) / F if F > 0 else float("nan")


def _result(method, model, base_y, adj, actual, cv, n, rep_daily_series=None):
    saved = float(adj.sum() - actual.sum())
    F = saved / float(adj.sum())
    m = len(actual)
    fsu = _fsu(cv, n, m, F)
    return dict(method=method, model=model, baseline_points=n, reporting_points=m, cv_rmse=float(cv),
                adjusted_baseline_kwh=float(adj.sum()), actual_kwh=float(actual.sum()),
                savings_kwh=saved, savings_pct=F, fsu_90=float(fsu),
                savings_low_kwh=saved * (1 - fsu), savings_high_kwh=saved * (1 + fsu),
                ashrae_ok=bool(fsu < 0.5))


def option_b(heats):
    base = heats[heats.day <= K.BASELINE_DAYS]
    rep = heats[heats.day > K.BASELINE_DAYS]
    Xb = np.column_stack([base.charge_kg, base.first_heat])
    beta, rmse, _ = _ols(Xb, base.furnace_kwh.values)
    adj = beta[0] + beta[1] * rep.charge_kg.values + beta[2] * rep.first_heat.values
    cv = rmse / base.furnace_kwh.mean()
    return _result("IPMVP Option B: retrofit isolation, furnace sub-meter, per heat",
                   f"kWh per heat = {beta[0]:.1f} + {beta[1]:.3f} x charge kg + {beta[2]:.1f} x first heat of day",
                   base.furnace_kwh, adj, rep.furnace_kwh.values, cv, len(base))


def option_c(daily):
    base = daily[daily.day <= K.BASELINE_DAYS]
    rep = daily[daily.day > K.BASELINE_DAYS]
    beta, rmse, _ = _ols(base[["liquid_t"]].values, base.plant_kwh.values)
    adj = beta[0] + beta[1] * rep.liquid_t.values
    cv = rmse / base.plant_kwh.mean()
    res = _result("IPMVP Option C: whole facility, main meter, per day (indicative)",
                  f"kWh per day = {beta[0]:.0f} + {beta[1]:.1f} x liquid tonnes",
                  base.plant_kwh, adj, rep.plant_kwh.values, cv, len(base))
    res["daily_adjusted"] = [float(v) for v in adj]
    res["daily_band_kwh"] = float(1.645 * rmse)
    return res
