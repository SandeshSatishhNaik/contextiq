"""Train/evaluate the decision model and the adaptive (bandit) layer on simulated scenarios.

Decision model: weights are learned by random search to agree with a written refund policy
(the kind a consumer-rights expert would apply), then tested on unseen scenarios. We also test
order-invariance and stability when weights are perturbed.

Adaptive layer: compares bandit strategies on simulated users whose preferences drift.
"""
from __future__ import annotations

import json

import numpy as np

from ..config import MODEL_DIR
from ..intelligence.decision import DEFAULT_WEIGHTS, benchmark_order_invariance, decide

R = lambda x: round(float(x), 3)  # noqa: E731
STATUSES = ["open", "closing", "expired", None]


def _scenario(rng):
    from ..agents.commerce import build_refund_options

    windows = {}
    for k, p in (("return_window", 0.8), ("replacement_window", 0.6), ("warranty", 0.7)):
        if rng.random() < p:
            windows[k] = {"status": str(rng.choice(["open", "closing", "expired"], p=[0.5, 0.2, 0.3]))}
    defect, captured = bool(rng.random() < 0.5), bool(rng.random() < 0.95)
    prefers_refund = bool(rng.random() < 0.3)
    conf = float(rng.uniform(0.3, 1.0))
    open_ = lambda k: windows.get(k, {}).get("status") in ("open", "closing")  # noqa: E731
    order = ["replacement_window", "return_window", "warranty"] if defect else ["return_window"]
    best_window = next((k for k in order if open_(k)), None)
    opts = build_refund_options(windows, defect, conf, captured, best_window, prefers_refund)
    # ground truth: written policy
    if not captured:
        truth = None
    elif defect and prefers_refund and open_("return_window"):
        truth = "request_refund"
    elif defect and open_("replacement_window"):
        truth = "request_replacement"
    elif open_("return_window"):
        truth = "request_refund"
    elif defect and open_("warranty"):
        truth = "warranty_claim"
    else:
        truth = "escalate_to_paypal_protection"
    return opts, truth


def _accuracy(scen, w) -> float:
    ok = 0
    for opts, truth in scen:
        c = decide(opts, w)["choice"]
        ok += int((c or {}).get("name") == truth)
    return ok / len(scen)


def evaluate_decision_model(seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    train = [_scenario(rng) for _ in range(800)]
    test = [_scenario(rng) for _ in range(800)]
    base_acc = _accuracy(test, DEFAULT_WEIGHTS)
    keys = list(DEFAULT_WEIGHTS)
    best_w, best_acc = dict(DEFAULT_WEIGHTS), _accuracy(train, DEFAULT_WEIGHTS)
    history = []
    for i in range(2500):  # random local search; step shrinks over time (coarse → fine)
        step = 0.25 if i < 800 else 0.1 if i < 1800 else 0.04
        cand = {k: best_w[k] + rng.normal(0, step) for k in keys}
        cand["risk"], cand["cost"] = -abs(cand["risk"]), -abs(cand["cost"])  # keep penalties as penalties
        acc = _accuracy(train, cand)
        if acc > best_acc:
            best_w, best_acc = cand, acc
            history.append({"iteration": i, "train_accuracy": R(acc)})
    test_acc = _accuracy(test, best_w)
    # robustness: perturb learned weights ±20% and see how often the decision stays the same
    same = 0
    for opts, _ in test[:300]:
        a = (decide(opts, best_w)["choice"] or {}).get("name")
        pw = {k: v * rng.uniform(0.8, 1.2) for k, v in best_w.items()}
        same += int((decide(opts, pw)["choice"] or {}).get("name") == a)
    invariance = np.mean([benchmark_order_invariance([o for o in opts], trials=10, seed=j)
                          for j, (opts, _) in enumerate(test[:100])])
    (MODEL_DIR / "decision_weights.json").write_text(json.dumps({"weights": {k: R(v) for k, v in best_w.items()},
                                                                 "train_accuracy": R(best_acc), "test_accuracy": R(test_acc)}))
    return {"method": "weighted scoring over permitted options; weights learned by random local search (2,500 steps, "
                      "Gaussian step 0.25 → 0.10 → 0.04, penalties constrained negative)",
            "hand_set_weights_test_accuracy": R(base_acc), "learned_weights_test_accuracy": R(test_acc),
            "learned_weights": {k: R(v) for k, v in best_w.items()}, "search_improvements": history[-5:],
            "order_invariance": R(invariance), "stable_under_20pct_weight_noise": R(same / 300),
            "ground_truth": "written refund policy (replacement for defects, refund on request or for non-defects, "
                            "warranty next, otherwise PayPal protection)"}


def evaluate_bandit(seed: int = 0, users: int = 150, rounds: int = 300, arms: int = 9) -> dict:
    rng = np.random.default_rng(seed)
    policies = {"fixed order": None, "random": None, "epsilon-greedy (eps=0.1)": 0.1,
                "UCB1": None, "Thompson sampling": None, "Thompson + forgetting (cap 50)": 50,
                "Thompson + forgetting (cap 200)": 200}
    totals = {p: 0.0 for p in policies}
    oracle = 0.0
    for _ in range(users):
        p_true = rng.beta(1, 4, arms)
        p_true[rng.integers(arms)] = rng.uniform(0.5, 0.8)
        drift_at = rounds // 2
        p_after = p_true.copy()
        p_after[rng.integers(arms)] = rng.uniform(0.6, 0.9)  # the user's routine changes
        draws = rng.random((rounds, arms))
        for name, param in policies.items():
            a = np.ones(arms); b = np.ones(arms); n = np.zeros(arms); s = np.zeros(arms)
            reward = 0.0
            for t in range(rounds):
                p = p_true if t < drift_at else p_after
                if name == "fixed order":
                    k = 0
                elif name == "random":
                    k = int(rng.integers(arms))
                elif name.startswith("epsilon"):
                    k = int(rng.integers(arms)) if rng.random() < param else int(np.argmax(s / np.maximum(n, 1)))
                elif name == "UCB1":
                    k = int(np.argmax(np.where(n == 0, np.inf, s / np.maximum(n, 1) + np.sqrt(2 * np.log(t + 1) / np.maximum(n, 1)))))
                else:
                    k = int(np.argmax(rng.beta(a, b)))
                r = float(draws[t, k] < p[k])
                reward += r
                n[k] += 1; s[k] += r; a[k] += r; b[k] += 1 - r
                if param and name.startswith("Thompson") and a[k] + b[k] > param:
                    scale = param / (a[k] + b[k]); a[k] *= scale; b[k] *= scale
            totals[name] += reward / rounds
        oracle += (p_true.max() * drift_at + p_after.max() * (rounds - drift_at)) / rounds
    res = {k: R(v / users) for k, v in totals.items()}
    best = max(res, key=res.get)
    return {"metric": "average tap rate on the top shortcut (higher is better)", "results": res,
            "best_possible_with_perfect_knowledge": R(oracle / users), "chosen": best,
            "setup": f"{users} simulated users, {arms} shortcuts, {rounds} visits each, preferences change halfway"}
