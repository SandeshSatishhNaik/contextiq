"""Re-calibrate the fraud layers' cut-offs against the scoring logic the app actually runs.

The thresholds saved by train.py were chosen against a narrower rule layer than runtime.fraud_score uses,
and on easier normal payments, so on a realistic stream more normal payments got an extra check than the
2% budget allowed. This picks the learned-model and anomaly cut-offs on a separate calibration stream
(its own seed; only the attack families used in training) so that, together with the runtime rules,
at most TARGET_FALSE_ALARM of normal payments are flagged, maximising attacks caught. The untouched
evaluation stream (evaluate_unseen, seed 2027) is never used here.

    python -m app.ml.calibrate_fraud            # report only
    python -m app.ml.calibrate_fraud --write    # also save the new cut-offs into fraud.joblib
"""
from __future__ import annotations

import json
import sys

import joblib
import numpy as np
import pandas as pd

from ..config import MODEL_DIR
from . import redteam, synth

CAL_SEED = 4242  # not used by training (37, 7, ...) or the final evaluation (2027)
TARGET_FALSE_ALARM = 0.025


def _rule_and_po(df: pd.DataFrame, rule_threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised copy of the rule layer and the invoice-above-PO hold in runtime.fraud_score."""
    urgent = df.urgency_score >= 0.5
    new_or_changed = (df.new_payee == 1) | (df.payee_changed_recently == 1)
    signal = (urgent & new_or_changed) | (df.urgency_score > 0.7)
    rule = np.minimum(1.0, 0.85 * signal + 0.5 * (df.payee_changed_recently == 1))
    return (rule >= rule_threshold).to_numpy(), (df.invoice_po_ratio > 1.05).to_numpy()


def _scores(bundle: dict, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = df[synth.FRAUD_FEATURES].astype(float)
    sup = bundle["supervised"].predict_proba(X)[:, 1]
    anom = 1 / (1 + np.exp(-12 * -bundle["isolation"].decision_function(X)))
    return sup, anom


def main(write: bool = False) -> dict:
    bundle = joblib.load(MODEL_DIR / "fraud.joblib")
    normal = synth.normal_fraud_rows(20000, seed=CAL_SEED)
    attacks = pd.concat([redteam.attacks(f, 200, seed=CAL_SEED + i, stealth=0.3)
                         for i, f in enumerate(redteam.TRAIN_FAMILIES)])
    sn, an = _scores(bundle, normal)
    sa, aa = _scores(bundle, attacks)
    rn, pn = _rule_and_po(normal, bundle["rule_threshold"])
    ra, pa = _rule_and_po(attacks, bundle["rule_threshold"])

    def rates(ts: float, ta: float) -> tuple[float, float]:
        fn = ((sn >= ts) | (an >= ta) | rn | pn).mean()
        fa = ((sa >= ts) | (aa >= ta) | ra | pa).mean()
        return float(fn), float(fa)

    old = bundle["thresholds"]
    before = rates(old["supervised"], old["anomaly"])
    floor = float((rn | pn).mean())  # false alarms the rules alone cause; cut-offs can't go below this
    best = (before[1] if before[0] <= TARGET_FALSE_ALARM else -1.0, old["supervised"], old["anomaly"])
    for qs in np.linspace(0.95, 0.9995, 40):
        ts = float(np.quantile(sn, qs))
        for qa in np.linspace(0.95, 0.9999, 40):
            ta = float(np.quantile(an, qa))
            fpr, rec = rates(ts, ta)
            if fpr <= TARGET_FALSE_ALARM and rec > best[0]:
                best = (rec, ts, ta)
    _, ts, ta = best
    after = rates(ts, ta)
    out = {"calibration_seed": CAL_SEED, "target_false_alarm": TARGET_FALSE_ALARM,
           "rules_only_false_alarm": round(floor, 4),
           "before": {"supervised": round(old["supervised"], 4), "anomaly": round(old["anomaly"], 4),
                      "false_alarm": round(before[0], 4), "caught": round(before[1], 4)},
           "after": {"supervised": round(ts, 4), "anomaly": round(ta, 4),
                     "false_alarm": round(after[0], 4), "caught": round(after[1], 4)}}
    if write:
        bundle["thresholds"] |= {"supervised": ts, "anomaly": ta, "calibrated_on": f"seed {CAL_SEED}, runtime logic"}
        joblib.dump(bundle, MODEL_DIR / "fraud.joblib")
        (MODEL_DIR / "fraud_calibration.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(json.dumps(main(write="--write" in sys.argv), indent=2))
