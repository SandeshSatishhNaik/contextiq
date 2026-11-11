"""Builds MODEL_REPORT.md from report.json + experiments.json (run automatically after training)."""
from __future__ import annotations

import json
from collections import defaultdict

from ..config import MODEL_DIR, ROOT

WHY = {
    "router": ("Turns a typed or spoken question into one of 10 topics so the right experts run.",
               "Short, messy text (typos, slang) → character n-grams handle spelling variation; word n-grams catch "
               "meaning. A soft-voting ensemble of both was best on phrasings never seen in training.",
               "Templated questions written by the team (~1,200), 4 phrasings per topic held out entirely."),
    "purpose": ("Decides whether a payment is personal or business.",
                "Logistic regression on text + time/amount features: fast, well-calibrated probabilities (needed to "
                "decide when to ask the user), and easy to explain.",
                "~15,000 synthetic transactions from 120 simulated users, 3% deliberately wrong labels."),
    "category": ("Puts each payment in a spending category for budgets.",
                 "Same design as purpose; class_weight='balanced' helps rarer categories.",
                 "Same transactions; test merchants have names the model never saw."),
    "fraud": ("Scores how risky a payment request is.",
              "Gradient boosting handles mixed signals (device, amount, payee changes) and their interactions well "
              "on tabular data; shallow trees (depth 2) generalised best. An isolation forest adds a check for "
              "'unlike anything normal', and two plain rules cover patterns that are rare but obvious.",
              "16,000 normal sessions + 5 attack types from a separate red-team generator; 2 attack types never "
              "shown to the model."),
    "subscription": ("Finds recurring payments (subscriptions, memberships).",
                     "Random forest on 5 timing/amount features; beats a hand-written rule mostly on recall "
                     "(it still finds subscriptions with a missed month or a price change).",
                     "5,000 payment histories incl. hard negatives such as weekly grocery shopping."),
    "forecaster": ("Predicts the next 30 days of everyday spending as a range.",
                   "Per-user spending profile, shrunk toward the population (helps users with little history), "
                   "plus bootstrapped day-to-day variation for the range.",
                   "180 days of daily spending for 80 simulated users; tuned on days 120–149, tested on 150–179."),
}
ROUNDS = [
    ("Round 1", "First models; router 0.56 macro-F1 on unseen phrasings; purpose/category/subscription ≈1.0.",
     "Scores near 1.0 meant the test was too easy, not that the models were good."),
    ("Round 2", "Harder tests: unseen users + unseen merchant names, held-out phrasings, label noise, hard negatives "
                "(weekly shopping), 10× more router phrasings.", "Router 0.70; purpose 0.94; category 0.89 — honest numbers."),
    ("Round 3", "Found a leak: the 'payee change' training attacks contained urgency wording, so the 'unseen' urgency "
                "attack wasn't really unseen. Removed it.", "Urgency attacks: learned model drops from 100% to 7% — "
                "the truth. Caught instead by a rule (71%)."),
    ("Round 4", "Hyperparameter search for every model (53 configurations); combined fraud layers by OR with "
                "per-layer thresholds instead of max-of-scores.", "Combined fraud no longer worse than its best layer."),
    ("Round 5", "Moved 'invoice above purchase order' out of the fraud score into the invoice check (where every "
                "mismatch is held anyway), freeing the false-alarm budget.", "Payee-change detection 66% → 91%."),
    ("Round 6", "Decision model stuck at 92%. Error analysis found a real bug: non-defective items were treated "
                "as eligible under the *replacement* window. Fixed in the app and the evaluator.",
     "Decision model 92% → 100% agreement with the written refund policy on unseen scenarios."),
    ("Round 7", "First test on realistic unseen data (100 hand-written messages, new seed, shifted conditions). Found that "
                "keyword rules made routing worse (77%) than the trained router alone (83%).",
     "Switched to router-first, rules only when the router is unsure (chosen on that development set: 84%). "
     "That set was then retired; final scores use a fresh set."),
    ("Round 8", "More realistic data: retail price points (.99), weekend dining, payday spending, night-time business "
                "payments, variable utility bills, big one-off purchases, casual/Indian-English phrasings, stealthier attackers.",
     "All models retrained; final unseen test uses seed 2027 and 100 brand-new questions."),
    ("Round 9", "LoRA policy model: first attempt memorised training wording (28–41% on unseen store styles). Added a "
                "third writing style for validation, augmentation and 2× pretraining.",
     "LoRA 54–56% (beats full fine-tune 48% with 25× fewer trainable weights); TF-IDF still best alone (79%). "
     "Ensemble 80% — deployed, gain within noise."),
]


def build() -> str:
    r = json.loads((MODEL_DIR / "report.json").read_text())
    exps = json.loads((MODEL_DIR / "experiments.json").read_text())
    by = defaultdict(list)
    for e in exps:
        by[e["model"]].append(e)
    L = ["# ContextIQ — model report", "",
         "Every model below was built, trained, evaluated and modified over nine rounds. Each was chosen by "
         "cross-validation on training data only, then scored once on a held-out test set built to be the hard "
         "case, and compared with a simple baseline. **All data is synthetic** (seeded, reproducible), so treat "
         "these as evidence the methods work, not as production accuracy.", "",
         f"Experiments run: **{r.get('n_experiments', len(exps))}** · training time: {r.get('training_seconds')} s on CPU.", "",
         "## Summary", "", "| Model | Chosen | Test result | Baseline |", "| --- | --- | --- | --- |"]
    ro = r["router"]
    L.append(f"| Question router | {ro['chosen']} | macro-F1 {ro['test_unseen_phrasings']['macro_f1']} on unseen phrasings | "
             f"{ro['baseline_majority_accuracy']} (random) |")
    for k in ("purpose", "category"):
        L.append(f"| {k.title()} | {r[k]['chosen']} | macro-F1 {r[k]['test']['macro_f1']} | {r[k]['baseline_majority']['macro_f1']} |")
    f = r["fraud"]
    fam = f["recall_per_family"]
    seen = [v["all three combined"] for v in fam.values() if v["seen_in_training"]]
    L.append(f"| Fraud | {f['chosen_learned_model']} + isolation forest + rules | {min(seen):.0%}–{max(seen):.0%} caught "
             f"(known attack types) at {f['false_alarm_rate_on_unseen_normal']['all three combined']:.1%} false alarms | — |")
    s = r["subscription"]
    L.append(f"| Subscriptions | {s['chosen']} | F1 {s['test']['f1']} | F1 {s['baseline_simple_rule']['f1']} (rule) |")
    fc = r["forecaster"]
    L.append(f"| Spending forecast | {fc['chosen']} | {fc['mape_30_day_total']:.1%} error | {fc['baseline_last_30_days_mape']:.1%} (repeat last month) |")
    d = r["decision_model"]
    L.append(f"| Decision model | learned weights | {d['learned_weights_test_accuracy']:.1%} agreement with written policy | "
             f"{d['hand_set_weights_test_accuracy']:.1%} (hand-set weights) |")
    b = r["adaptive_bandit"]
    L.append(f"| Adaptive layer | {b['chosen']} | {b['results'][b['chosen']]:.0%} tap rate | {b['results']['fixed order']:.0%} (fixed order) |")
    L += ["", "## How the models improved, round by round", "", "| Round | What changed | Effect |", "| --- | --- | --- |"]
    L += [f"| {a} | {b_} | {c} |" for a, b_, c in ROUNDS]

    for key, title in (("router", "Question router"), ("purpose", "Personal vs business"), ("category", "Spending category"),
                       ("fraud", "Fraud detection"), ("subscription", "Subscription detector"), ("forecaster", "Spending forecast")):
        what, why, data = WHY[key]
        L += ["", f"## {title}", "", f"**What it does:** {what}", "", f"**Data:** {data}", "", f"**Why this design:** {why}", "",
              "**Every configuration tried** (cross-validated):", "", "| Candidate | Hyperparameters | CV score | Chosen |",
              "| --- | --- | --- | --- |"]
        rows = sorted(by.get(key, []), key=lambda e: -e["cv_score"] if "lower" not in e["metric"] else e["cv_score"])
        for e in rows:
            params = ", ".join(f"{k}={v}" for k, v in e["params"].items())
            L.append(f"| {e['candidate']} | {params} | {e['cv_score']} ({e['metric']}) | {'yes' if e['chosen'] else ''} |")
        if key == "fraud":
            L += ["", "**Share of attacks caught on the test set** (false alarms held near 2%):", "",
                  "| Attack type | Seen in training | Learned model | Anomaly detector | Rules | All combined |",
                  "| --- | --- | --- | --- | --- | --- |"]
            for k2, v in fam.items():
                L.append(f"| {k2.replace('_', ' ')} | {'yes' if v['seen_in_training'] else 'no'} | {v['learned model']:.0%} | "
                         f"{v['anomaly detector']:.0%} | {v['rules']:.0%} | {v['all three combined']:.0%} |")
            L += ["", f"Invoice inflation is caught by the invoice-vs-purchase-order check: "
                      f"{f.get('invoice_check_catches_inflation', 1.0):.0%}. The fraud models themselves don't catch it — "
                      "say so in the pitch.", "",
                  f"PR-AUC on all test data: learned model {f['pr_auc_all_families']['learned model']}, "
                  f"anomaly detector {f['pr_auc_all_families']['anomaly detector']}."]
        if key == "router":
            t = ro["test_unseen_phrasings"]
            L += ["", f"Test on unseen phrasings: accuracy {t['accuracy']}, macro-F1 {t['macro_f1']}. In the app, keyword "
                      "rules answer first; the router handles the rest; below 0.25 confidence the reasoning model (Groq/Claude) "
                      "is asked, or the user gets a short \"did you mean…\" question."]
        if key == "purpose" and "confusion_matrix" in r["purpose"]:
            cm = r["purpose"]["confusion_matrix"]
            L += ["", "Confusion matrix (rows = truth):", "", "| | predicted personal | predicted business |", "| --- | --- | --- |",
                  f"| personal | {cm['matrix'][0][0]} | {cm['matrix'][0][1]} |", f"| business | {cm['matrix'][1][0]} | {cm['matrix'][1][1]} |"]
        if key == "forecaster":
            L += ["", f"Test: {fc['mape_30_day_total']:.1%} error on the 30-day total; the P10–P90 range contained the real "
                      f"amount for {fc['p10_p90_range_contains_actual']:.0%} of users (ideal: 80%)."]

    L += ["", "## Decision model", "", "**What it does:** ranks the options experts propose (for example refund, replacement, "
          "warranty repair, PayPal protection) and recommends one. Options the store's terms don't allow are never ranked.", "",
          f"**Method:** {d['method']}.", "", f"**Ground truth:** {d['ground_truth']}.", "",
          "| Check | Result |", "| --- | --- |",
          f"| Agreement with written policy, hand-set weights | {d['hand_set_weights_test_accuracy']:.1%} |",
          f"| Agreement with written policy, learned weights | {d['learned_weights_test_accuracy']:.1%} |",
          f"| Same answer when options are shuffled | {d['order_invariance']:.0%} |",
          f"| Same answer when weights are jittered ±20% | {d['stable_under_20pct_weight_noise']:.1%} |", "",
          "Learned weights: " + ", ".join(f"{k} {v}" for k, v in d["learned_weights"].items()) + ".", "",
          "Order-invariance matters: LLM-as-judge setups are known to change answers when options are reordered. "
          "This model can't, by construction.",
          "", "## Adaptive layer (reinforcement learning)", "",
          "**What it does:** learns which shortcuts and reminder times each user actually uses. It only reorders and "
          "times things; it can never change permissions, limits or payments.", "",
          f"**Setup:** {b['setup']}.", "", "| Strategy | Tap rate |", "| --- | --- |"]
    L += [f"| {k} | {v:.1%} |" for k, v in sorted(b["results"].items(), key=lambda x: -x[1])]
    L += [f"| best possible (knows the future) | {b['best_possible_with_perfect_knowledge']:.1%} |", "",
          f"Chosen: **{b['chosen']}**. The app caps each option's evidence (forgetting) so it keeps adapting when routines change, "
          "and clips each feedback event so a burst of fake taps can't take over.", ""]
    L += _lora_section() + _unseen_section()
    L += ["", "## Limits", "",
          "- All training data is synthetic; real data will be messier and scores will drop.",
          "- Next: external fraud check on PaySim / IEEE-CIS public datasets.",
          "- Regenerate this report any time with `python -m app.ml.train`."]
    return "\n".join(L) + "\n"


def _lora_section() -> list[str]:
    path = MODEL_DIR / "lora_report.json"
    if not path.exists():
        return ["## LoRA policy model", "", "Not trained yet — run `python -m app.ml.lora_policy`."]
    r = json.loads(path.read_text())
    pre = r["pretraining"]
    L = ["## LoRA policy model (PyTorch + peft)", "",
         "**What it does:** labels each sentence of a store policy (return window, replacement, warranty, exclusion, "
         "condition, return shipping, refund method, other) so plain code can read the numbers from the right sentences.", "",
         f"**Base model:** a {pre['encoder_params']:,}-parameter byte-level Transformer (3 layers, 4 heads, width 128) "
         f"pretrained from scratch with masked-byte modelling on {pre['texts']:,} unlabelled shopping/finance texts "
         f"({pre['epochs']} epochs, lr {pre['lr']}, loss {pre['mlm_loss_start']} → {pre['mlm_loss_end']}). No pretrained model "
         "could be downloaded in the build environment.", "",
         f"**Data:** {r['train_sentences']:,} training sentences (with augmentation), validation on a *different* writing style, "
         f"test on {r['unseen_test_sentences']} sentences in store styles never seen.", "",
         "| Approach | Trainable parameters | Dev-style accuracy | Unseen-style accuracy | Unseen macro-F1 |", "| --- | --- | --- | --- | --- |"]
    for k, v in r["results"].items():
        tp = f"{v['trainable_params']:,}" if v["trainable_params"] else "—"
        L.append(f"| {k} | {tp} | {v['val_accuracy']:.1%} | {v['unseen_accuracy']:.1%} | {v['unseen_macro_f1']} |")
    L += ["", f"Deployed: TF-IDF + LoRA ({r['best_neural_on_dev']}) ensemble, weight chosen on the dev style. LoRA settings: "
          "rank r, alpha = 2r, dropout 0.05, applied to the attention query and value projections, classifier head trained, "
          "AdamW lr 3e-3, up to 6 epochs with the best epoch picked on the dev style.", "",
          "**Honest reading:** LoRA did what it is designed to do — it matched or beat full fine-tuning while training "
          "25–90× fewer weights — but a small model pretrained from scratch doesn't know enough language to beat simple "
          "n-gram features on new wording. With a real pretrained model (on a machine that can download one) the same "
          "`peft` code applies unchanged."]
    return L


def _unseen_section() -> list[str]:
    path = MODEL_DIR / "unseen_report.json"
    if not path.exists():
        return []
    u = json.loads(path.read_text())
    ro, tx, fr, sb, fc, de, ba = u["router"], u["transactions"], u["fraud"], u["subscriptions"], u["forecast"], u["decision"], u["bandit"]
    L = ["", "## Final test on unseen data", "",
         f"Fresh random seed ({u['seed']}), shifted conditions, and 100 brand-new hand-written questions. Nothing here was "
         "used for training, tuning or any design decision.", "",
         "| Model | Shift | Result |", "| --- | --- | --- |",
         f"| Question routing (as the app runs it) | 100 new casual / Indian-English / typo messages | accuracy {ro['app_model_then_rules']['accuracy']:.0%}, macro-F1 {ro['app_model_then_rules']['macro_f1']} |",
         f"| Personal vs business | new users, new merchant naming style, 30% of business payments at night | macro-F1 {tx['purpose']['macro_f1']} (night-time business payments recognised: {tx.get('business_payments_at_night_recognised', 0):.0%}) |",
         f"| Spending category | same | macro-F1 {tx['category']['macro_f1']} |",
         f"| Fraud | realistic 1% fraud rate, stealthier attackers | catches {fr['caught_recall']:.0%}; {fr['precision_of_alerts']:.0%} of alerts are real fraud; "
         f"{fr['false_alarm_rate']:.1%} of normal payments get an extra check ({fr['alerts_per_1000_payments']:.0f} alerts per 1,000 payments) |",
         f"| Subscriptions | 35% variable utility bills (5% in training) | precision {sb['precision']}, recall {sb['recall']}, F1 {sb['f1']} |",
         f"| 30-day forecast | new users with big one-off purchases | error {fc['mape_30_day']:.0%}; range right for {fc['range_contains_actual']:.0%} of users |",
         f"| Decision model | new scenario mix | {de['agreement_with_policy']:.1%} agreement with the written policy |",
         f"| Adaptive layer | new users | {ba['thompson']:.0%} tap rate vs {ba['fixed_order']:.0%} fixed order (perfect knowledge: {ba['best_possible']:.0%}) |",
         "", "Fraud caught by attack type (stealthier versions): " + ", ".join(
             f"{k.replace('_', ' ')} {v:.0%}" for k, v in fr["caught_per_attack_type_stealthier"].items()) + ".",
         "", "Routing per topic on the new questions: " + ", ".join(f"{k.replace('_', ' ')} {v:.0%}" for k, v in ro["per_topic_accuracy_app"].items()) + "."]
    if ro.get("examples_wrong"):
        L += ["", "Examples it still gets wrong:", ""] + [f"- \"{e['text']}\" → {e['got']} (should be {e['truth']})" for e in ro["examples_wrong"][:5]]
    return L


def write() -> None:
    (ROOT / "MODEL_REPORT.md").write_text(build())


if __name__ == "__main__":
    write()
