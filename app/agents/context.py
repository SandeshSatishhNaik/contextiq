"""Context expert: channel, personal vs business purpose, profile suggestion, fraud features."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ml import runtime
from ..models import LedgerEntry, User


def classify(db: Session, user_id: str, payee: str, description: str, channel: str, amount: float,
             when: datetime | None = None) -> dict:
    when = when or datetime.now(UTC)
    user = db.get(User, user_id)
    owner = bool(user and user.role in ("merchant", "supplier", "business_owner") or (user and user.business_name))
    out = runtime.classify_transaction(payee, description, channel, when.hour, when.weekday(), amount, owner)
    profile = "business" if out["purpose"] == "business" else "personal"
    out["suggested_profile"] = profile
    out["why"] = (f"{'Business' if profile == 'business' else 'Personal'} looks likely from the payee and description"
                  + (", even outside your usual working hours" if profile == "business" and user and
                     not (user.work_start_hour <= when.hour < user.work_end_hour) else "") + ".")
    if out["purpose_confidence"] < 0.7:
        out["why"] += " Low confidence — please confirm."
    return out


def fraud_features(db: Session, user_id: str, payee: str, amount: float, *, invoice_po_ratio: float = 1.0,
                   text: str = "", new_device: bool = False, ip_country_mismatch: bool = False,
                   payee_changed_recently: bool = False, session_age_min: float = 30.0,
                   when: datetime | None = None) -> dict:
    when = when or datetime.now(UTC)
    hist = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0)).all()
    amounts = np.array([h.amount for h in hist]) if hist else np.array([amount])
    mu, sd = float(np.mean(amounts)), float(np.std(amounts) or max(1.0, np.mean(amounts) * 0.5))
    user = db.get(User, user_id)
    hours_ok = user and (min(user.work_start_hour, 7) <= when.hour <= 23)
    recent = [h for h in hist if (when - (h.occurred_at if h.occurred_at.tzinfo else
                                          h.occurred_at.replace(tzinfo=UTC))).total_seconds() < 3600]
    return {
        "amount_z": (amount - mu) / sd, "log_amount": float(np.log1p(amount)),
        "new_payee": int(not any(h.payee == payee for h in hist)),
        "payee_changed_recently": int(payee_changed_recently), "new_device": int(new_device),
        "ip_country_mismatch": int(ip_country_mismatch), "unusual_hour": int(not hours_ok),
        "burst_1h": len(recent), "invoice_po_ratio": invoice_po_ratio,
        "urgency_score": runtime.urgency_score(text), "session_age_min": session_age_min,
    }


def assess_risk(db: Session, user_id: str, payee: str, amount: float, **signals) -> dict:
    feats = fraud_features(db, user_id, payee, amount, **signals)
    res = runtime.fraud_score(feats)
    res["features"] = {k: round(v, 3) if isinstance(v, float) else v for k, v in feats.items()}
    return res
