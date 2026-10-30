"""Hybrid NILM: the furnace and compressor are sub-metered, and the residual
(mains minus sub-meters) is disaggregated into individual auxiliary loads.

Model: one gradient-boosted sequence-to-point regressor per load. Input is a
5-minute window of residual power around each timestamp plus edge and rolling
features; output is that load's power at the window centre. Labels come from
the commissioning week, when portable clamp meters record each machine.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from . import config as K

HALF = 15  # +/- 15 samples at 10 s = 5-minute window


def features(residual, minute, furnace=None, on_kw=20.0, hi_kw=300.0):
    x = np.asarray(residual, float)
    n = len(x)
    pad = np.pad(x, HALF, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, 2 * HALF + 1)[:n]
    win = win[:, ::3]  # 11 samples across the window
    d = np.diff(pad)[HALF - 1:HALF - 1 + n]
    s = pd.Series(x)
    feats = [win, win - x[:, None], d[:, None]]
    for w in (6, 30, 90):
        r = s.rolling(w, center=True, min_periods=1)
        feats += [r.mean().values[:, None], r.std().fillna(0).values[:, None],
                  r.max().values[:, None], r.min().values[:, None]]
    ang = 2 * np.pi * np.asarray(minute) / 1440
    feats += [np.sin(ang)[:, None], np.cos(ang)[:, None]]
    if furnace is not None:
        # hybrid metering: the furnace sub-meter tells the model when the furnace is
        # melting or energised, which drives the cooling pump and fume extraction
        f = pd.Series(np.asarray(furnace, float))
        on = (f > on_kw).astype(float)
        melting = (f > hi_kw).astype(float)
        feats += [on.values[:, None], melting.values[:, None],
                  on.rolling(120, min_periods=1).max().values[:, None],   # energised in the last 20 min
                  melting.rolling(18, center=True, min_periods=1).mean().values[:, None]]
    return np.hstack(feats)


class HybridNILM:
    """loads: machine names. on_kw / hi_kw: thresholds for the metered big load's
    'on' and 'full power' states (foundry defaults: 20 kW energised, 300 kW melting).
    use_metered=False runs without any sub-meter input (pure NILM)."""

    def __init__(self, loads, on_kw=20.0, hi_kw=300.0, use_metered=True):
        self.loads = loads
        self.models = {}
        self.on_kw, self.hi_kw, self.use_metered = on_kw, hi_kw, use_metered

    def _X(self, ts):
        f = ts.furnace_kw.values if self.use_metered else None
        return features(ts.residual_kw.values, ts.minute.values, f, self.on_kw, self.hi_kw)

    def fit(self, ts):
        X = self._X(ts)
        for k in self.loads:
            m = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.08, max_leaf_nodes=48,
                                              random_state=K.SEED)
            m.fit(X, ts[f"{k}_kw"].values)
            self.models[k] = m
        return self

    def predict(self, ts):
        X = self._X(ts)
        P = np.column_stack([np.clip(self.models[k].predict(X), 0, None) for k in self.loads])
        # physics rules from commissioning: the cooling pump only runs while the furnace is
        # energised or for 20 minutes after; fume extraction only runs while melting
        f = pd.Series(ts.furnace_kw.values)
        energised_recent = (f > 20).astype(float).rolling(125, min_periods=1).max().values > 0
        melting_near = (f > 300).astype(float).rolling(7, center=True, min_periods=1).max().values > 0
        rules = {"cooling_pump": energised_recent, "fume_extraction": melting_near}
        for j, k in enumerate(self.loads):
            if k in rules:
                P[:, j] = P[:, j] * rules[k]
        # energy conservation: rescale so loads add up to the measured residual
        tot = P.sum(1)
        res = np.clip(ts.residual_kw.values, 0, None)
        scale = np.where(tot > 0.5, res / np.maximum(tot, 1e-6), 1.0)
        P = P * np.clip(scale, 0.7, 1.3)[:, None]
        return pd.DataFrame(P, columns=self.loads, index=ts.index)


def evaluate(true_df, pred_df, loads, on_kw=0.5):
    """on_kw: on/off threshold for F1, one value or a dict per load."""
    out = []
    dt_h = K.DT_S / 3600
    total_true = sum(true_df[f"{k}_kw"].sum() for k in loads) * dt_h
    for k in loads:
        t = true_df[f"{k}_kw"].values
        p = pred_df[k].values
        e_t, e_p = t.sum() * dt_h, p.sum() * dt_h
        th = on_kw[k] if isinstance(on_kw, dict) else on_kw
        on_t, on_p = t > th, p > th
        tp = (on_t & on_p).sum()
        prec = tp / max(on_p.sum(), 1)
        rec = tp / max(on_t.sum(), 1)
        out.append(dict(load=k, mae_kw=float(np.abs(t - p).mean()),
                        nde=float(np.sqrt(((t - p) ** 2).sum() / max((t ** 2).sum(), 1e-9))),
                        energy_true_kwh=float(e_t), energy_pred_kwh=float(e_p),
                        sae=float(abs(e_p - e_t) / max(e_t, 1e-9)),
                        share_true=float(e_t / total_true), share_pred=float(e_p / total_true),
                        f1_on_off=float(2 * prec * rec / max(prec + rec, 1e-9))))
    return pd.DataFrame(out)


class ShareBaseline:
    """Naive comparison model: every machine gets a fixed share of the residual load,
    learned from the commissioning days. Any useful NILM model must beat this."""

    def __init__(self, loads):
        self.loads = loads
        self.share = {}

    def fit(self, ts):
        tot = ts.residual_kw.clip(lower=0).sum()
        self.share = {k: ts[f"{k}_kw"].sum() / tot for k in self.loads}
        return self

    def predict(self, ts):
        r = ts.residual_kw.clip(lower=0).values
        return pd.DataFrame({k: r * self.share[k] for k in self.loads}, index=ts.index)


def confidence_tier(sae, f1):
    """Label each machine estimate so nobody over-reads a number."""
    if sae <= 0.05 and f1 >= 0.90:
        return "High"
    if sae <= 0.15 and f1 >= 0.75:
        return "Medium"
    return "Low"
