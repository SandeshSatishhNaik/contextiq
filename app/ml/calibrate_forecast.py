"""Widen the forecaster's p10-p90 range until it really contains ~80% of outcomes.

The simulation resamples days independently, so streaky weeks and payday spikes are missed and the raw range
is too narrow (it contained the actual 30-day spend only ~72% of the time). This picks the smallest widening
factor that reaches TARGET coverage on a calibration population with its own seed; the final evaluation's
seed (2027) is never used here.

    python -m app.ml.calibrate_forecast            # report only
    python -m app.ml.calibrate_forecast --write    # also save range_scale into forecaster.joblib
"""
from __future__ import annotations

import json
import sys

import joblib
import numpy as np

from ..config import MODEL_DIR
from . import synth
from .forecast import CashFlowForecaster

CAL_SEED = 5151
TARGET = 0.80


def main(write: bool = False) -> dict:
    saved = joblib.load(MODEL_DIR / "forecaster.joblib")
    df = synth.make_daily_spend(n_users=300, seed=CAL_SEED)
    g = CashFlowForecaster(profile=saved.profile, shrink=saved.shrink).fit(df[df.day < 150])
    rows = []
    for u, grp in df[df.day >= 150].groupby("user"):
        fc = g.forecast_user(u, 30, 150 % 7)
        rows.append((fc["p10"], fc["p50"], fc["p90"], grp.spend.sum()))
    p10, p50, p90, actual = map(np.array, zip(*rows, strict=True))

    def coverage(k: float) -> float:
        return float(((np.maximum(0, p50 - k * (p50 - p10)) <= actual) & (actual <= p50 + k * (p90 - p50))).mean())

    k = next((round(float(x), 2) for x in np.arange(1.0, 3.01, 0.05) if coverage(x) >= TARGET), 3.0)
    out = {"calibration_seed": CAL_SEED, "users": len(rows), "target_coverage": TARGET,
           "coverage_before": round(coverage(1.0), 3), "range_scale": k, "coverage_after": round(coverage(k), 3)}
    if write:
        saved.range_scale = k
        joblib.dump(saved, MODEL_DIR / "forecaster.joblib")
        (MODEL_DIR / "forecast_calibration.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(json.dumps(main(write="--write" in sys.argv), indent=2))
