"""ContextIQ decision model: constrained, transparent scoring of bounded alternatives.

Input: options with features in [0, 1] and a `permitted` flag from the gateway pre-check.
Output: ranked options, each with its score breakdown. Deterministic and order-invariant by
construction (the score of an option never depends on where it sits in the list) — the property
LLM-as-judge setups often lack. benchmark_order_invariance() demonstrates it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

DEFAULT_WEIGHTS = {
    "benefit": 0.30,          # money saved / problem solved
    "risk": -0.25,            # financial or fraud risk
    "urgency": 0.15,          # deadline pressure that this option addresses
    "reversibility": 0.10,    # can it be undone
    "evidence": 0.15,         # confidence of the evidence it relies on
    "user_preference": 0.05,  # matches stated preferences
    "cost": -0.10,            # fees, effort, interruption
}


def _learned_weights() -> dict[str, float]:
    try:
        import json

        from ..config import MODEL_DIR

        w = json.loads((MODEL_DIR / "decision_weights.json").read_text())["weights"]
        return {k: float(v) for k, v in w.items()}
    except Exception:  # noqa: BLE001 — fall back to hand-set weights before training
        return dict(DEFAULT_WEIGHTS)


@dataclass
class Option:
    name: str
    features: dict[str, float]
    permitted: bool = True
    explanation: str = ""
    action: dict = field(default_factory=dict)


def score(opt: Option, weights: dict[str, float] | None = None) -> tuple[float, dict]:
    weights = weights or ACTIVE_WEIGHTS
    parts = {k: round(w * float(opt.features.get(k, 0.0)), 4) for k, w in weights.items()}
    return round(sum(parts.values()), 4), parts


def decide(options: list[Option], weights: dict[str, float] | None = None, margin: float = 0.03) -> dict:
    ranked = []
    for o in options:
        s, parts = score(o, weights)
        ranked.append({"name": o.name, "score": s if o.permitted else None, "permitted": o.permitted,
                       "breakdown": parts, "explanation": o.explanation, "action": o.action})
    allowed = sorted([r for r in ranked if r["permitted"]], key=lambda r: (-r["score"], r["name"]))
    blocked = [r for r in ranked if not r["permitted"]]
    if not allowed:
        return {"choice": None, "ranked": blocked, "confidence": "none", "needs_human": True}
    close = len(allowed) > 1 and allowed[0]["score"] - allowed[1]["score"] < margin
    return {"choice": allowed[0], "ranked": allowed + blocked,
            "confidence": "low" if close else "high", "needs_human": close}


def benchmark_order_invariance(options: list[Option], trials: int = 50, seed: int = 0) -> float:
    """Fraction of shuffled orderings that produce the same choice (1.0 = fully invariant)."""
    rng = random.Random(seed)
    base = decide(options)["choice"]
    same = 0
    for _ in range(trials):
        opts = options[:]
        rng.shuffle(opts)
        c = decide(opts)["choice"]
        same += int((c or {}).get("name") == (base or {}).get("name"))
    return same / trials


ACTIVE_WEIGHTS = _learned_weights()
