"""Cash-flow forecaster: learned weekday spending profile + bootstrap residuals → ranges."""
from __future__ import annotations

import numpy as np
import pandas as pd


class CashFlowForecaster:
    def __init__(self, n_sims: int = 400, seed: int = 0, profile: str = "weekday", shrink: float = 0.0,
                 range_scale: float = 1.0):
        """profile: 'weekday' learns a per-weekday level, 'flat' a single daily level.
        shrink: pull each user's profile toward the population profile (helps users with little history).
        range_scale: widens the p10-p90 range around the median. Days are resampled independently, which
        misses streaky weeks and payday spikes, so the raw range is too narrow; calibrate_forecast.py sets it."""
        self.n_sims, self.seed, self.profile, self.shrink = n_sims, seed, profile, shrink
        self.range_scale = range_scale
        self.profiles: dict[str, np.ndarray] = {}
        self.residuals: dict[str, np.ndarray] = {}
        self.global_profile = np.ones(7) * 30.0
        self.global_resid = np.zeros(1)

    def fit(self, df: pd.DataFrame) -> CashFlowForecaster:
        """df columns: user, day, weekday, spend (daily discretionary spending)."""
        self.global_profile = df.groupby("weekday").spend.mean().reindex(range(7)).to_numpy()
        for user, g in df.groupby("user"):
            if self.profile == "flat":
                prof = np.full(7, g.spend.mean())
            else:
                prof = g.groupby("weekday").spend.mean().reindex(range(7)).fillna(g.spend.mean()).to_numpy()
            scale = g.spend.mean() / max(self.global_profile.mean(), 1e-9)
            prof = (1 - self.shrink) * prof + self.shrink * self.global_profile * scale
            self.profiles[user] = prof
            self.residuals[user] = (g.spend.to_numpy() - prof[g.weekday.to_numpy()])
        self.global_resid = (df.spend - self.global_profile[df.weekday]).to_numpy()
        return self

    def fit_ledger(self, user: str, daily: pd.Series) -> None:
        """Personalise from a user's own ledger (index = date, value = spend)."""
        if len(daily) < 14:
            return
        wd = np.array([d.weekday() for d in daily.index])
        prof = np.array([daily.values[wd == k].mean() if (wd == k).any() else daily.mean() for k in range(7)])
        self.profiles[user] = prof
        self.residuals[user] = daily.values - prof[wd]

    def forecast_user(self, user: str, horizon: int = 30, start_weekday: int = 0) -> dict:
        prof = self.profiles.get(user, self.global_profile)
        resid = self.residuals.get(user, self.global_resid)
        rng = np.random.default_rng(self.seed)
        wds = (start_weekday + np.arange(horizon)) % 7
        base = prof[wds]
        sims = np.maximum(0, base + rng.choice(resid, size=(self.n_sims, horizon))).sum(axis=1)
        p10, p50, p90 = (float(np.quantile(sims, q)) for q in (0.1, 0.5, 0.9))
        k = getattr(self, "range_scale", 1.0)  # older pickles have no attribute
        return {"expected": float(base.sum()), "p10": max(0.0, p50 - k * (p50 - p10)), "p50": p50,
                "p90": p50 + k * (p90 - p50), "horizon_days": horizon, "personalised": user in self.profiles}
