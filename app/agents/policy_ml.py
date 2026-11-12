"""Model-assisted policy reading: classify each sentence (TF-IDF + LoRA ensemble), then read numbers with code.
Handles wording the fixed patterns miss, e.g. "Easy 10 day returns, no questions asked."."""
from __future__ import annotations

import json
import re

import numpy as np

from ..config import MODEL_DIR

WORDS = {"seven": 7, "ten": 10, "fourteen": 14, "fifteen": 15, "thirty": 30, "sixty": 60, "ninety": 90, "one": 1,
         "two": 2, "three": 3, "six": 6, "twelve": 12}
_models = None


def _load():
    global _models
    if _models is None:
        import joblib

        tf = joblib.load(MODEL_DIR / "policy_tfidf.joblib") if (MODEL_DIR / "policy_tfidf.joblib").exists() else None
        w = json.loads((MODEL_DIR / "policy_ensemble.json").read_text())["weight_neural"] if (MODEL_DIR / "policy_ensemble.json").exists() else 0.0
        _models = (tf, w)
    return _models


def classify(sents: list[str]) -> list[tuple[str, float]]:
    from ..ml import policy_data

    tf, w = _load()
    if tf is None or not sents:
        return []
    p = tf.predict_proba(sents)
    if w > 0:
        try:
            import torch

            from ..ml import lora_policy as L

            L.classify_sentences(sents[:1])
            m, _ = L._clf
            with torch.no_grad():
                pn = m(input_ids=L.encode(sents)).softmax(-1).numpy()
            p = w * pn + (1 - w) * p
        except Exception:  # noqa: BLE001 — torch missing: TF-IDF alone
            pass
    return [(policy_data.LABELS[int(i)], float(p[k, i])) for k, i in enumerate(np.argmax(p, 1))]


def _duration_days(s: str) -> int | None:
    m = re.search(r"(\d+|" + "|".join(WORDS) + r")\s*(?:-|\s)?\s*(calendar |working |business )?(day|month|year)s?", s, re.I)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else WORDS[m.group(1).lower()]
    unit = m.group(3).lower()
    return n if unit == "day" else n * 365 if unit == "year" else round(n * 365 / 12)  # 12 months = 365 days


def extract(text: str) -> dict:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 3]
    labels = classify(sents)
    out = {"return_window_days": None, "replacement_window_days": None, "warranty_days": None, "starts_from": "purchase",
           "exclusions": [], "conditions": [], "return_shipping_paid_by": "unknown", "refund_method": "unknown",
           "sentences": [{"text": s, "type": l, "confidence": round(c, 2)} for s, (l, c) in zip(sents, labels)]}
    key = {"return_window": "return_window_days", "replacement": "replacement_window_days", "warranty": "warranty_days"}
    for s, (lab, conf) in zip(sents, labels):
        if conf < 0.35:
            continue
        if lab in key and out[key[lab]] is None:
            out[key[lab]] = _duration_days(s)
            if lab in ("return_window", "replacement") and re.search(r"deliver|receipt|recei?ved|arriv", s, re.I):
                out["starts_from"] = "delivery"
        elif lab == "exclusion":
            out["exclusions"].append(s)
        elif lab == "condition":
            out["conditions"].append(s)
        elif lab == "shipping_cost":
            out["return_shipping_paid_by"] = "merchant" if re.search(r"free|prepaid", s, re.I) else "buyer"
        elif lab == "refund_method" and re.search(r"original|source|card|paypal", s, re.I):
            out["refund_method"] = "original payment method"
    return out
