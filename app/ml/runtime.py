"""Loads trained specialist models once and exposes small prediction helpers."""
from __future__ import annotations

import re
from functools import cache

import joblib
import numpy as np
import pandas as pd

from ..config import MODEL_DIR
from .synth import FRAUD_FEATURES, series_features, urgency_score


@cache
def _load(name: str):
    path = MODEL_DIR / f"{name}.joblib"
    if not path.exists():
        from .train import main

        main()
    return joblib.load(path)


def route_intent(text: str) -> tuple[str, float]:
    m = _load("router")
    proba = m.predict_proba([text])[0]
    i = int(np.argmax(proba))
    return str(m.classes_[i]), float(proba[i])


# Well-known merchants and unambiguous words beat the category model, which was trained on synthetic
# merchant names and is weak on real brands. Order matters: the first match wins ("uber eats" is dining).
CATEGORY_KEYWORDS: list[tuple[str, re.Pattern]] = [(cat, re.compile(pat, re.I)) for cat, pat in [
    ("dining", r"\b(uber ?eats|doordash|grubhub|restaurant|cafe|caf[eé]|coffee|starbucks|dinner|lunch|breakfast|"
               r"chipotle|mcdonald'?s|pizza|burger|takeaway|takeout|bar & grill)\b"),
    ("groceries", r"\b(grocer(y|ies)|supermarket|whole foods|trader joe'?s|safeway|kroger|aldi|costco|"
                  r"weekly shop|instacart)\b"),
    ("transport", r"\b(uber|lyft|taxi|cab|ride home|airline|flight|airfare|train|metro|subway|bus pass|parking|"
                  r"toll|fuel|petrol|gas station|shell|chevron)\b"),
    ("utilities", r"\b(electric(ity)?|power bill|water bill|gas bill|utility|utilities|internet|broadband|"
                  r"comcast|xfinity|pg&e|pacific gas|phone bill|mobile plan)\b"),
    ("entertainment", r"\b(netflix|spotify|hulu|disney\+?|hbo|cinema|movie|concert|tickets?|steam|playstation|"
                      r"xbox|nintendo|streaming)\b"),
    ("health", r"\b(pharmacy|cvs|walgreens|prescription|doctor|dentist|dental|clinic|hospital|gym|fitness)\b"),
    ("logistics", r"\b(fedex|ups|dhl|usps|courier|freight|shipping|postage|delivery fee)\b"),
    ("software", r"\b(aws|amazon web services|azure|google cloud|github|gitlab|adobe|slack|notion|atlassian|"
                 r"saas|cloud hosting|web hosting|domain renewal|software licen[cs]e)\b"),
    ("supplies", r"\b(office depot|staples|toner|printer paper|stationery|office supplies)\b"),
    ("electronics", r"\b(best buy|apple store|laptop|smartphone|headphones|earbuds|camera|monitor|keyboard|"
                    r"electronics)\b"),
    ("clothing", r"\b(zara|h&m|uniqlo|nike|adidas|clothing|apparel|shoes|sneakers|jacket)\b"),
    ("inventory", r"\b(wholesale|inventory|stock purchase|resale stock|sensor boards?|parts order)\b"),
    ("services", r"\b(consulting|cleaning service|plumber|electrician|repair service|legal fees?|accountant|"
                 r"bookkeeping)\b"),
]]
CATEGORY_MIN_CONFIDENCE = 0.5  # below this, and with no keyword, the category is left for the user to set


def category_from_keywords(text: str) -> str | None:
    return next((cat for cat, rx in CATEGORY_KEYWORDS if rx.search(text)), None)


def classify_transaction(payee: str, description: str, channel: str, hour: int, weekday: int, amount: float,
                         business_owner: bool) -> dict:
    X = pd.DataFrame([{"text": f"{payee} | {description} | {channel}", "hour": hour, "weekday": weekday,
                       "log_amount": float(np.log1p(amount)), "business_owner": int(business_owner),
                       "in_hours": int(9 <= hour < 18)}])
    out = {}
    for target in ("purpose", "category"):
        m = _load(f"{target}_classifier")
        p = m.predict_proba(X)[0]
        i = int(np.argmax(p))
        out[target] = str(m.classes_[i])
        out[f"{target}_confidence"] = round(float(p[i]), 3)
    out["category_model_guess"] = out["category"]
    kw = category_from_keywords(f"{payee} {description}")
    if kw:
        out["category"], out["category_source"] = kw, "keyword"
        out["category_confidence"] = max(out["category_confidence"], 0.9) if kw == out["category_model_guess"] else 0.9
    elif out["category_confidence"] < CATEGORY_MIN_CONFIDENCE:
        out["category"], out["category_source"] = "uncategorized", "unsure"
    else:
        out["category_source"] = "model"
    return out


def fraud_score(features: dict) -> dict:
    """Three independent layers; a payment is flagged when any layer fires (thresholds set in training
    so that, together, about 2% of normal payments get an extra check)."""
    bundle = _load("fraud")
    X = pd.DataFrame([{f: float(features.get(f, 0.0)) for f in FRAUD_FEATURES}])
    sup = float(bundle["supervised"].predict_proba(X)[0, 1])
    anom = float(1 / (1 + np.exp(-12 * -bundle["isolation"].decision_function(X)[0])))
    urgent = features.get("urgency_score", 0) >= 0.5
    new_or_changed = bool(features.get("new_payee")) or bool(features.get("payee_changed_recently"))
    over_po = features.get("invoice_po_ratio", 1.0) > 1.05
    urgent_payment_signal = (urgent and new_or_changed) or (features.get("urgency_score", 0) > 0.7) or (urgent and features.get("amount_z", 0) > 1.0)
    rule = min(1.0, 0.85 * urgent_payment_signal + 0.5 * bool(features.get("payee_changed_recently")))
    t = bundle["thresholds"]
    fired = {"learned model": sup >= t["supervised"], "anomaly detector": anom >= t["anomaly"],
             "rules": rule >= bundle["rule_threshold"]}
    reasons = []
    if over_po:
        reasons.append(f"the invoice is {features['invoice_po_ratio']:.0%} of what was agreed")
    if urgent:
        reasons.append("the message pushes you to pay urgently")
    if features.get("payee_changed_recently"):
        reasons.append("the payee's bank or account details changed recently")
    if features.get("new_device"):
        reasons.append("you're on a device we haven't seen before")
    if features.get("ip_country_mismatch"):
        reasons.append("you seem to be connecting from a different country than usual")
    if features.get("amount_z", 0) > 3:
        reasons.append("the amount is much higher than you usually pay")
    if features.get("new_payee"):
        reasons.append("you haven't paid this payee before")
    n_fired = sum(fired.values())
    strong = sum((over_po, urgent and new_or_changed, bool(features.get("payee_changed_recently")),
                  features.get("amount_z", 0) > 3))
    if over_po:  # invoice above the agreed amount is always held (dispute prevention), independent of the models
        n_fired = max(n_fired, 1)
    decision = "review" if (n_fired >= 2 and strong >= 2) or (over_po and strong >= 2) else "step_up" if n_fired else "allow"
    return {"decision": decision, "layers_fired": [k for k, v in fired.items() if v],
            "score": round(max(sup, anom, rule), 3),
            "components": {"learned model": round(sup, 3), "anomaly detector": round(anom, 3), "rules": round(rule, 3)},
            "reasons": reasons or ["nothing unusual about this payment"],
            "note": "These are warning signs, not proof. A location or network change alone never blocks a payment."}


def is_subscription(days: list[float], amounts: list[float]) -> tuple[bool, float]:
    if len(days) < 3:
        return False, 0.0
    b = _load("subscription")
    X = pd.DataFrame([series_features(days, amounts)])[b["features"]]
    p = float(b["model"].predict_proba(X)[0, 1])
    return p >= 0.5, round(p, 3)


def forecaster():
    return _load("forecaster")


__all__ = ["route_intent", "classify_transaction", "fraud_score", "is_subscription", "forecaster", "urgency_score"]
