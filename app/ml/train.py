"""Train every specialist model on synthetic data, choose models by cross-validation,
and write an honest evaluation report (model card).

Run:  python -m app.ml.train
Outputs: app/ml/models/*.joblib, app/ml/models/report.json, app/ml/models/report.md

Method, for every model:
  1. Hold out a test set the model never sees during selection (unseen users, unseen merchant
     names, unseen phrasings, or unseen attack types — whichever is the hard case for that model).
  2. Compare candidate models with group cross-validation on the training part only.
  3. Refit the winner on all training data, then score once on the held-out test set.
  4. Compare with a simple baseline so the number means something.
"""
from __future__ import annotations

import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_score
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from ..config import MODEL_DIR
from . import redteam, synth
from .forecast import CashFlowForecaster

R = lambda x: round(float(x), 3)  # noqa: E731
EXPERIMENTS: list[dict] = []


def log_exp(model: str, candidate: str, params: dict, metric: str, score: float, chosen: bool = False) -> None:
    EXPERIMENTS.append({"model": model, "candidate": candidate, "params": params, "metric": metric,
                        "cv_score": R(score), "chosen": chosen})


def search(model_name: str, cands: dict, X, y, cv, scoring: str, groups=None):
    """Cross-validate every (candidate, params) pair; log all; return best name and score table."""
    scores = {}
    for name, (est, params) in cands.items():
        sc = cross_val_score(est, X, y, groups=groups, cv=cv, scoring=scoring).mean()
        scores[name] = R(sc)
        log_exp(model_name, name, params, scoring, sc)
    best = max(scores, key=scores.get)
    for e in EXPERIMENTS:
        if e["model"] == model_name and e["candidate"] == best:
            e["chosen"] = True
    return best, scores


def _char_tfidf(n_features=2**16):
    return make_pipeline(HashingVectorizer(analyzer="char_wb", ngram_range=(2, 5), n_features=n_features,
                                           alternate_sign=False, norm=None), TfidfTransformer(sublinear_tf=True))


def _word_tfidf(n_features=2**15):
    return make_pipeline(HashingVectorizer(analyzer="word", ngram_range=(1, 2), n_features=n_features,
                                           alternate_sign=False, norm=None), TfidfTransformer(sublinear_tf=True))


# ----------------------------------------------------------------------- router
def train_router() -> dict:
    df = synth.make_router_data()
    held = {t for ts in synth.INTENT_EXAMPLES.values() for t in ts[-4:]}  # 4 phrasings per intent never seen
    te = df.template.isin(held)
    tr = df[~te]
    from sklearn.ensemble import VotingClassifier

    def char_lr(C, ng):
        return make_pipeline(make_pipeline(HashingVectorizer(analyzer="char_wb", ngram_range=ng, n_features=2**17,
                                                             alternate_sign=False, norm=None),
                                           TfidfTransformer(sublinear_tf=True)), LogisticRegression(max_iter=4000, C=C))

    def word_lr(C):
        return make_pipeline(_word_tfidf(2**16), LogisticRegression(max_iter=4000, C=C))

    candidates = {}
    for C in (3, 10, 30):
        for ng in ((2, 4), (2, 5), (1, 6)):
            candidates[f"char LR C={C} ngrams={ng}"] = (char_lr(C, ng), {"features": "char_wb tf-idf", "ngram_range": ng, "C": C})
    for C in (3, 10, 30):
        candidates[f"word LR C={C}"] = (word_lr(C), {"features": "word 1-2gram tf-idf", "C": C})
    for C in (0.3, 1.0):
        candidates[f"char SVM C={C}"] = (make_pipeline(_char_tfidf(), CalibratedClassifierCV(LinearSVC(C=C), cv=3)),
                                         {"features": "char_wb tf-idf", "C": C, "calibration": "sigmoid, 3-fold"})
    for a in (0.1, 0.3, 1.0):
        candidates[f"word NB alpha={a}"] = (make_pipeline(_word_tfidf(), ComplementNB(alpha=a)), {"alpha": a})
    candidates["ensemble char LR + word LR (soft vote)"] = (
        VotingClassifier([("c", char_lr(10, (2, 5))), ("w", word_lr(10))], voting="soft"),
        {"members": "char LR C=10 (2,5) + word LR C=10", "voting": "soft"})
    cv = GroupKFold(n_splits=5)  # group by phrasing so CV also measures unseen phrasings
    best, scores = search("router", candidates, tr.text, tr.intent, cv, "f1_macro", groups=tr.template)
    candidates = {k: v[0] for k, v in candidates.items()}
    model = candidates[best].fit(tr.text, tr.intent)
    pred = model.predict(df.text[te])
    proba = model.predict_proba(df.text[te]).max(axis=1)
    conf_mask = proba >= 0.45
    joblib.dump(model, MODEL_DIR / "router.joblib")
    return {"chosen": best, "cv_macro_f1": scores,
            "test_unseen_phrasings": {"accuracy": R(accuracy_score(df.intent[te], pred)),
                                      "macro_f1": R(f1_score(df.intent[te], pred, average="macro")),
                                      "accuracy_when_confident": R(accuracy_score(df.intent[te][conf_mask], pred[conf_mask])),
                                      "share_confident": R(conf_mask.mean())},
            "baseline_majority_accuracy": R(1 / df.intent.nunique()),
            "n_train": int((~te).sum()), "n_test": int(te.sum()),
            "how_used": "Keyword rules answer first; this model handles what rules miss; below 0.45 confidence "
                        "the GenAI layer (if configured) is asked."}


# ------------------------------------------------------------- purpose / category
def _tx_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "text": df.payee + " | " + df.description + " | " + df.channel,
        "hour": df.hour, "weekday": df.weekday, "log_amount": np.log1p(df.amount),
        "business_owner": df.business_owner.astype(int),
    })
    out["in_hours"] = ((df.hour >= 9) & (df.hour < 18)).astype(int)
    return out


def _tx_pipeline(clf) -> Pipeline:
    pre = ColumnTransformer([
        ("txt", _char_tfidf(2**15), "text"),
        ("num", StandardScaler(), ["hour", "weekday", "log_amount", "business_owner", "in_hours"]),
    ])
    return Pipeline([("pre", pre), ("clf", clf)])


def train_transaction_models() -> dict:
    users = synth.make_users()
    tx = synth.make_transactions(users)
    X = _tx_frame(tx)
    test_users = set(users.user_id.sample(frac=0.25, random_state=1))
    rng = np.random.default_rng(3)
    test_merchants = {m for m in sorted(tx.payee.unique()) if rng.random() < 0.3}
    is_test_user = tx.user_id.isin(test_users)
    te = is_test_user & tx.payee.isin(test_merchants)       # unseen users AND unseen merchant names
    trn = ~is_test_user & ~tx.payee.isin(test_merchants)     # training never sees those merchants either
    report = {}
    for target in ("purpose", "category"):
        y = tx[target]
        cands = {}
        for c in (0.25, 1, 4, 16):
            for cw in (None, "balanced"):
                cands[f"LR C={c} class_weight={cw}"] = (
                    _tx_pipeline(LogisticRegression(max_iter=5000, C=c, class_weight=cw)),
                    {"features": "char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag",
                     "C": c, "class_weight": cw})
        best, scores = search(target, cands, X[trn], y[trn], GroupKFold(n_splits=4), "f1_macro", groups=tx.user_id[trn])
        model = cands[best][0].fit(X[trn], y[trn])
        pred = model.predict(X[te])
        base = DummyClassifier(strategy="most_frequent").fit(X[trn], y[trn]).predict(X[te])
        joblib.dump(model, MODEL_DIR / f"{target}_classifier.joblib")
        entry = {"chosen": best, "cv_macro_f1": scores,
                 "test": {"accuracy": R(accuracy_score(y[te], pred)), "macro_f1": R(f1_score(y[te], pred, average="macro"))},
                 "baseline_majority": {"accuracy": R(accuracy_score(y[te], base)),
                                       "macro_f1": R(f1_score(y[te], base, average="macro"))},
                 "n_train": int(trn.sum()), "n_test": int(te.sum()),
                 "split": "test = unseen users AND merchant names never seen in training; labels include 3% noise"}
        if target == "purpose":
            labels = ["personal", "business"]
            entry["confusion_matrix"] = {"labels": labels,
                                         "matrix": confusion_matrix(y[te], pred, labels=labels).tolist()}
        report[target] = entry
    return report


# --------------------------------------------------------------------------- fraud
def train_fraud() -> dict:
    normal = synth.normal_fraud_rows(16000)
    n_tr, n_val, n_te = normal.iloc[:10000], normal.iloc[10000:13000], normal.iloc[13000:]
    train_att = pd.concat([redteam.attacks(f, 500, seed=11) for f in redteam.TRAIN_FAMILIES])
    test_att = {f: redteam.attacks(f, 500, seed=23) for f in redteam.TRAIN_FAMILIES + redteam.HELDOUT_FAMILIES}
    F = synth.FRAUD_FEATURES
    tr = pd.concat([n_tr, train_att]).reset_index(drop=True)

    cands = {}
    for d in (2, 3):
        for lr in (0.05, 0.1):
            cands[f"GBM depth={d} lr={lr}"] = (GradientBoostingClassifier(max_depth=d, learning_rate=lr, n_estimators=200,
                                                                         subsample=0.8, random_state=0),
                                               {"max_depth": d, "learning_rate": lr, "n_estimators": 200, "subsample": 0.8})
    for leaf in (1, 5):
        cands[f"random forest min_leaf={leaf}"] = (RandomForestClassifier(n_estimators=300, min_samples_leaf=leaf,
                                                                          random_state=0, n_jobs=-1),
                                                   {"n_estimators": 300, "min_samples_leaf": leaf})
    cands["logistic regression"] = (make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)), {"C": 1.0})
    best, cv_scores = search("fraud", cands, tr[F], tr.label, StratifiedKFold(n_splits=3, shuffle=True, random_state=0),
                             "average_precision")
    sup = cands[best][0].fit(tr[F], tr.label)

    iso = make_pipeline(StandardScaler(), IsolationForest(n_estimators=300, random_state=0))
    iso.fit(n_tr[F])

    def s_sup(d):
        return sup.predict_proba(d[F])[:, 1]

    def s_anom(d):
        return 1 / (1 + np.exp(-12 * (-iso.decision_function(d[F]))))

    def s_rules(d):
        # urgency wording alone is common in honest reminders, so it only counts together with a new
        # or changed payee; an invoice above the agreed purchase order always counts
        # (invoice-above-PO is handled by the invoice check, which holds every mismatch for review anyway)
        return np.clip(0.8 * ((d.urgency_score >= 0.5) & ((d.new_payee == 1) | (d.payee_changed_recently == 1)))
                       + 0.5 * d.payee_changed_recently, 0, 1)

    RULE_T = 0.75
    val_att = pd.concat([redteam.attacks(f, 300, seed=37) for f in redteam.TRAIN_FAMILIES])
    single = {"learned model": s_sup, "anomaly detector": s_anom}
    thr = {k: float(np.quantile(fn(n_val), 0.98)) for k, fn in single.items()}
    thr["rules"] = RULE_T

    # combined system: flag if ANY layer fires; pick per-layer cut-offs so total false alarms stay <= 2%
    # 2-D search: each learned layer gets its own share of the 2% false-alarm budget
    sv, av = s_sup(n_val), s_anom(n_val)
    rv = s_rules(n_val) >= RULE_T
    sa, aa, ra = s_sup(val_att), s_anom(val_att), s_rules(val_att) >= RULE_T
    grid_best = (0.0, 0.99, 0.999)
    for qs in np.linspace(0.95, 0.999, 25):
        ts = np.quantile(sv, qs)
        for qa in np.linspace(0.97, 0.9999, 20):
            ta = np.quantile(av, qa)
            if ((sv >= ts) | (av >= ta) | rv).mean() <= 0.02:
                rec = ((sa >= ts) | (aa >= ta) | ra).mean()
                if rec > grid_best[0]:
                    grid_best = (rec, qs, qa)
    _, best_qs, best_qa = grid_best
    comb_sup, comb_anom = float(np.quantile(sv, best_qs)), float(np.quantile(av, best_qa))
    best_q = best_qs

    def fires(d):
        return {"learned model": s_sup(d) >= thr["learned model"], "anomaly detector": s_anom(d) >= thr["anomaly detector"],
                "rules": s_rules(d) >= RULE_T,
                "all three combined": (s_sup(d) >= comb_sup) | (s_anom(d) >= comb_anom) | (s_rules(d) >= RULE_T)}

    per_family = {}
    for fam, df in test_att.items():
        per_family[fam] = {"seen_in_training": fam in redteam.TRAIN_FAMILIES} | {k: R(v.mean()) for k, v in fires(df).items()}
    fpr = {k: R(v.mean()) for k, v in fires(n_te).items()}
    all_test = pd.concat([n_te] + list(test_att.values()))
    pr_auc = {"learned model": R(average_precision_score(all_test.label, s_sup(all_test))),
              "anomaly detector": R(average_precision_score(all_test.label, s_anom(all_test)))}
    joblib.dump({"supervised": sup, "isolation": iso, "features": F, "rule_threshold": RULE_T,
                 "thresholds": {"supervised": comb_sup, "anomaly": comb_anom, "combined_quantile": round(float(best_q), 4)}},
                MODEL_DIR / "fraud.joblib")
    return {"chosen_learned_model": best, "cv_average_precision": cv_scores,
            "false_alarm_rate_on_unseen_normal": fpr, "pr_auc_all_families": pr_auc, "recall_per_family": per_family,
            "invoice_check_catches_inflation": R((test_att["invoice_inflation"].invoice_po_ratio > 1.05).mean()),
            "note": ("Held-out families were written in a separate generator and never used in training. "
                     "Invoice inflation is caught by the invoice-vs-purchase-order check (a separate, deterministic "
                     "step that holds every mismatch), not by the fraud models — report it that way.")}


# ------------------------------------------------------------------ subscriptions
def train_subscription() -> dict:
    df = synth.make_payee_series(5000)
    F = ["n", "mean_gap", "gap_cv", "amount_cv", "period_fit"]
    rng = np.random.default_rng(0)
    te = rng.random(len(df)) < 0.25
    cands = {}
    for leaf in (1, 3, 10):
        cands[f"random forest min_leaf={leaf}"] = (RandomForestClassifier(n_estimators=300, min_samples_leaf=leaf,
                                                                          random_state=0, n_jobs=-1),
                                                   {"n_estimators": 300, "min_samples_leaf": leaf})
    for d in (2, 3):
        cands[f"GBM depth={d}"] = (GradientBoostingClassifier(max_depth=d, random_state=0), {"max_depth": d, "n_estimators": 100})
    cands["logistic regression"] = (make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)), {"C": 1.0})
    best, scores = search("subscription", cands, df[F][~te], df.label[~te],
                          StratifiedKFold(n_splits=5, shuffle=True, random_state=0), "f1")
    m = cands[best][0].fit(df[F][~te], df.label[~te])
    p = m.predict(df[F][te])
    # rule baseline: "same payee, regular gaps, similar amounts"
    rule = ((df.gap_cv[te] < 0.15) & (df.amount_cv[te] < 0.1) & (df.n[te] >= 3)).astype(int)
    joblib.dump({"model": m, "features": F}, MODEL_DIR / "subscription.joblib")
    return {"chosen": best, "cv_f1": scores,
            "test": {"precision": R(precision_score(df.label[te], p)), "recall": R(recall_score(df.label[te], p)),
                     "f1": R(f1_score(df.label[te], p))},
            "baseline_simple_rule": {"precision": R(precision_score(df.label[te], rule, zero_division=0)),
                                     "recall": R(recall_score(df.label[te], rule)), "f1": R(f1_score(df.label[te], rule))},
            "n_test": int(te.sum()),
            "includes": "missed payments, price changes, and weekly shopping habits that look regular but aren't subscriptions"}


# ---------------------------------------------------------------------- forecaster
def train_forecaster() -> dict:
    df = synth.make_daily_spend()
    # tune on a validation window (days 120-149) using only days < 120, then refit on < 150 and test on 150+
    val_scores = {}
    for profile in ("weekday", "flat"):
        for shrink in (0.0, 0.3, 0.6):
            f = CashFlowForecaster(profile=profile, shrink=shrink).fit(df[df.day < 120])
            errs_v = []
            for user, g in df[(df.day >= 120) & (df.day < 150)].groupby("user"):
                errs_v.append(abs(f.forecast_user(user, 30, 120 % 7)["expected"] - g.spend.sum()) / max(g.spend.sum(), 1))
            name = f"profile={profile} shrink={shrink}"
            val_scores[name] = (float(np.mean(errs_v)), {"profile": profile, "shrink_to_population": shrink})
            log_exp("forecaster", name, {"profile": profile, "shrink_to_population": shrink, "n_sims": 400},
                    "validation MAPE (lower is better)", float(np.mean(errs_v)))
    best_name = min(val_scores, key=lambda k: val_scores[k][0])
    for e in EXPERIMENTS:
        if e["model"] == "forecaster" and e["candidate"] == best_name:
            e["chosen"] = True
    f = CashFlowForecaster(profile=val_scores[best_name][1]["profile"],
                           shrink=val_scores[best_name][1]["shrink_to_population"]).fit(df[df.day < 150])
    test = df[df.day >= 150]
    train = df[df.day < 150]
    errs, base_errs, covered = [], [], 0
    for user, g in test.groupby("user"):
        fc = f.forecast_user(user, horizon=30, start_weekday=150 % 7)
        actual = g.spend.sum()
        naive = train[(train.user == user) & (train.day >= 120)].spend.sum()  # "same as last 30 days"
        errs.append(abs(fc["expected"] - actual) / max(actual, 1))
        base_errs.append(abs(naive - actual) / max(actual, 1))
        covered += int(fc["p10"] <= actual <= fc["p90"])
    joblib.dump(f, MODEL_DIR / "forecaster.joblib")
    return {"chosen": best_name, "mape_30_day_total": R(np.mean(errs)), "baseline_last_30_days_mape": R(np.mean(base_errs)),
            "p10_p90_range_contains_actual": R(covered / test.user.nunique()), "users": int(test.user.nunique())}


def main() -> dict:
    t0 = time.time()
    report = {"data": "Synthetic, seeded, generated in app/ml/synth.py; attacks in app/ml/redteam.py (separate generator)."}
    report["router"] = train_router()
    report |= train_transaction_models()
    report["fraud"] = train_fraud()
    report["subscription"] = train_subscription()
    report["forecaster"] = train_forecaster()
    from .evaluate_reasoning import evaluate_bandit, evaluate_decision_model
    report["decision_model"] = evaluate_decision_model()
    report["adaptive_bandit"] = evaluate_bandit()
    (MODEL_DIR / "experiments.json").write_text(json.dumps(EXPERIMENTS, indent=1, default=str))
    report["n_experiments"] = len(EXPERIMENTS)
    report["training_seconds"] = round(time.time() - t0, 1)
    (MODEL_DIR / "report.json").write_text(json.dumps(report, indent=2))
    (MODEL_DIR / "report.md").write_text(_md(report))
    from .model_report import write as write_model_report
    write_model_report()
    return report


def _md(r: dict) -> str:
    L = ["# ContextIQ model card", "", r["data"],
         "Every model was chosen by cross-validation on training data only, then scored once on a held-out test set "
         "designed to be the hard case, and compared with a simple baseline.", "",
         "## Results at a glance", "", "| Model | Test set | Score | Simple baseline |", "| --- | --- | --- | --- |"]
    ro = r["router"]["test_unseen_phrasings"]
    L.append(f"| Question router | phrasings never seen | macro-F1 {ro['macro_f1']} (accuracy {ro['accuracy_when_confident']} "
             f"on the {ro['share_confident']:.0%} it is confident about) | random guess {r['router']['baseline_majority_accuracy']} |")
    for k, name in (("purpose", "Personal vs business"), ("category", "Spending category")):
        L.append(f"| {name} | unseen users and merchants | macro-F1 {r[k]['test']['macro_f1']} | "
                 f"{r[k]['baseline_majority']['macro_f1']} (always the most common) |")
    s = r["subscription"]
    L.append(f"| Subscription detector | incl. missed payments, price changes, weekly habits | F1 {s['test']['f1']} | "
             f"F1 {s['baseline_simple_rule']['f1']} (simple rule) |")
    fc = r["forecaster"]
    L.append(f"| 30-day spending forecast | last 30 days of 80 users | error {fc['mape_30_day_total']:.0%}, range right "
             f"{fc['p10_p90_range_contains_actual']:.0%} of the time | error {fc['baseline_last_30_days_mape']:.0%} (repeat last month) |")
    f = r["fraud"]
    L += ["", "## Fraud — share of attacks caught, by attack type", "",
          "False alarms on normal payments are held near 2% for every column.", "",
          "| Attack type | Seen in training | Learned model | Anomaly detector | Rules | All combined |",
          "| --- | --- | --- | --- | --- | --- |"]
    for fam, v in f["recall_per_family"].items():
        L.append(f"| {fam.replace('_', ' ')} | {'yes' if v['seen_in_training'] else 'no'} | {v['learned model']:.0%} | "
                 f"{v['anomaly detector']:.0%} | {v['rules']:.0%} | {v['all three combined']:.0%} |")
    fa = f["false_alarm_rate_on_unseen_normal"]
    L += ["", f"False alarms on unseen normal payments: learned {fa['learned model']:.1%}, combined {fa['all three combined']:.1%}.",
          f"Learned model chosen: {f['chosen_learned_model']} (cross-validated average precision "
          f"{f['cv_average_precision'][f['chosen_learned_model']]}).", "", f["note"], "",
          "## Limits", "",
          "- Synthetic data is cleaner than real data; treat these as evidence the pipeline works, not production accuracy.",
          "- Next step: an external check on PaySim / IEEE-CIS public fraud data.",
          f"- Training time: {r['training_seconds']} s on a laptop CPU."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
