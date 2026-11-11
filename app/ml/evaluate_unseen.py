"""Final evaluation on UNSEEN data — different random seed, shifted conditions, nothing reused from
training or model selection. Run after training:  python -m app.ml.evaluate_unseen

Shifts per model:
  router        100 hand-written realistic messages (casual, Indian English, typos)
  purpose/cat.  new users, merchant names from a different naming style, more night-time business payments
  fraud         realistic stream: 1% fraud among normal payments, stealthier attackers (fewer red flags)
  subscriptions adds variable monthly utility bills and different mix
  forecast      new users, payday spending spikes
  decision      new scenario mix
  bandit        new user population
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from ..config import MODEL_DIR
from . import redteam, synth
from .unseen_questions import UNSEEN, UNSEEN_FINAL

SEED = 2027  # fresh seed for the final run (2026 was used during development)
R = lambda x: round(float(x), 3)  # noqa: E731


def router(bank: dict | None = None) -> dict:
    """Scores exactly what the app does: trained router first, keyword rule only when the router is unsure."""
    import re

    from ..orchestrator import RULE_FALLBACK_BELOW, RULES

    bank = bank or UNSEEN_FINAL
    texts = [t for ts in bank.values() for t in ts]
    y = [k for k, ts in bank.items() for _ in ts]
    m = joblib.load(MODEL_DIR / "router.joblib")
    P = m.predict_proba(texts)
    pred_model = list(m.classes_[P.argmax(1)])
    conf = P.max(1)

    def full(t, p, c):
        if re.search(r"\b(never made|didn'?t authorize|did not authorize|not me|unauthorized|stolen|hacked|fake charge)\b", t.lower()):
            return "fraud"
        if c < RULE_FALLBACK_BELOW:
            for pat, intent in RULES:
                if re.search(pat, t.lower()):
                    return intent
        return p
    pred_app = [full(t, p, c) for t, p, c in zip(texts, pred_model, conf)]
    per = {k: R(np.mean([pa == k for pa, yy in zip(pred_app, y) if yy == k])) for k in bank}
    return {"n": len(texts), "model_alone": {"accuracy": R(accuracy_score(y, pred_model)),
                                             "macro_f1": R(f1_score(y, pred_model, average="macro"))},
            "app_model_then_rules": {"accuracy": R(accuracy_score(y, pred_app)),
                                     "macro_f1": R(f1_score(y, pred_app, average="macro"))},
            "per_topic_accuracy_app": per,
            "examples_wrong": [{"text": t, "truth": yy, "got": pa} for t, yy, pa in zip(texts, y, pred_app) if yy != pa][:8]}


def transactions() -> dict:
    from .train import _tx_frame

    users = synth.make_users(80, seed=SEED)
    tx = synth.make_transactions(users, seed=SEED, merchant_prefixes=synth._PREFIX_UNSEEN, night_business=0.3)
    X = _tx_frame(tx)
    out = {"n": len(tx)}
    for target in ("purpose", "category"):
        m = joblib.load(MODEL_DIR / f"{target}_classifier.joblib")
        p = m.predict(X)
        out[target] = {"accuracy": R(accuracy_score(tx[target], p)), "macro_f1": R(f1_score(tx[target], p, average="macro"))}
    biz_night = (tx.purpose == "business") & (tx.hour >= 20)
    if biz_night.any():
        p = joblib.load(MODEL_DIR / "purpose_classifier.joblib").predict(X[biz_night])
        out["business_payments_at_night_recognised"] = R((p == "business").mean())
    return out


def fraud() -> dict:
    from .runtime import fraud_score

    rng = np.random.default_rng(SEED)
    normal = synth.normal_fraud_rows(9900, seed=SEED)
    fams = redteam.TRAIN_FAMILIES + redteam.HELDOUT_FAMILIES
    att = pd.concat([redteam.attacks(f, 20, seed=SEED + i, stealth=0.3) for i, f in enumerate(fams)])
    stream = pd.concat([normal, att]).sample(frac=1, random_state=SEED).reset_index(drop=True)  # 1% fraud
    decisions = [fraud_score(r)["decision"] for r in stream[synth.FRAUD_FEATURES].to_dict("records")]
    flagged = np.array([d != "allow" for d in decisions])
    y = stream.label.to_numpy()
    per = {f: R(flagged[(stream.family == f).to_numpy()].mean()) for f in fams}
    _ = rng
    return {"n_payments": len(stream), "fraud_rate": R(y.mean()),
            "caught_recall": R(recall_score(y, flagged)), "precision_of_alerts": R(precision_score(y, flagged)),
            "false_alarm_rate": R(flagged[y == 0].mean()), "alerts_per_1000_payments": R(flagged.mean() * 1000),
            "caught_per_attack_type_stealthier": per,
            "note": "Invoice inflation is handled by the invoice check, which holds every invoice above its PO."}


def subscriptions() -> dict:
    df = synth.make_payee_series(3000, seed=SEED, utility_share=0.35)
    b = joblib.load(MODEL_DIR / "subscription.joblib")
    p = b["model"].predict(df[b["features"]])
    return {"n": len(df), "precision": R(precision_score(df.label, p)), "recall": R(recall_score(df.label, p)),
            "f1": R(f1_score(df.label, p)), "shift": "35% of recurring items are variable utility bills (5% in training)"}


def forecast() -> dict:
    df = synth.make_daily_spend(n_users=60, seed=SEED)
    f = joblib.load(MODEL_DIR / "forecaster.joblib")
    from .forecast import CashFlowForecaster

    g = CashFlowForecaster(profile=f.profile, shrink=f.shrink).fit(df[df.day < 150])
    errs, cov = [], 0
    for u, grp in df[df.day >= 150].groupby("user"):
        fc = g.forecast_user(u, 30, 150 % 7)
        a = grp.spend.sum()
        errs.append(abs(fc["expected"] - a) / max(a, 1))
        cov += int(fc["p10"] <= a <= fc["p90"])
    return {"users": int(df.user.nunique()), "mape_30_day": R(np.mean(errs)), "range_contains_actual": R(cov / df.user.nunique())}


def decision() -> dict:
    from ..intelligence.decision import decide
    from .evaluate_reasoning import _scenario

    w = json.loads((MODEL_DIR / "decision_weights.json").read_text())["weights"]
    rng = np.random.default_rng(SEED)
    sc = [_scenario(rng) for _ in range(1000)]
    ok = sum(int(((decide(o, w)["choice"] or {}).get("name")) == t) for o, t in sc)
    return {"n": len(sc), "agreement_with_policy": R(ok / len(sc))}


def bandit() -> dict:
    from .evaluate_reasoning import evaluate_bandit

    r = evaluate_bandit(seed=SEED, users=100)
    return {"thompson": r["results"]["Thompson sampling"], "fixed_order": r["results"]["fixed order"],
            "best_possible": r["best_possible_with_perfect_knowledge"]}


def main() -> dict:
    res = {"seed": SEED, "router_dev_set": router(UNSEEN), "router": router(UNSEEN_FINAL), "transactions": transactions(), "fraud": fraud(),
           "subscriptions": subscriptions(), "forecast": forecast(), "decision": decision(), "bandit": bandit()}
    (MODEL_DIR / "unseen_report.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
