"""Personal / business account intelligence.

1. If the user already told us how they file this payee, use that — no question.
2. Otherwise the trained classifier decides; if it's unsure, or the payment is large, ask one short question.
A classification never authorizes a payment or changes a funding source on its own.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PayeePreference, now
from . import context as ctx_agent

ASK_IF_CONFIDENCE_BELOW = 0.75
ASK_IF_AMOUNT_AT_LEAST = 500.0


def classify_with_memory(db: Session, user_id: str, payee: str, description: str, channel: str, amount: float,
                         when: datetime | None = None) -> dict:
    pref = db.scalar(select(PayeePreference).where(PayeePreference.user_id == user_id, PayeePreference.payee == payee))
    if pref:
        return {"purpose": pref.purpose, "source": "your earlier choice", "needs_confirmation": False,
                "why": f"You've filed {payee} as {pref.purpose} before, so I used that.",
                "suggested_profile": pref.purpose, "purpose_confidence": 1.0}
    out = ctx_agent.classify(db, user_id, payee, description, channel, amount, when or datetime.now(UTC))
    ask = out["purpose_confidence"] < ASK_IF_CONFIDENCE_BELOW or amount >= ASK_IF_AMOUNT_AT_LEAST
    # Never ask: file it automatically and show "Filed as X · change". Low confidence only makes the
    # change link more prominent in the app.
    out |= {"source": "learned model", "needs_confirmation": False, "low_confidence": ask,
            "filed_note": f"Filed as {out['purpose']}" + (" — tap to change if that's wrong" if ask else "")}
    return out


def remember(db: Session, user_id: str, payee: str, purpose: str) -> dict:
    assert purpose in ("personal", "business")
    pref = db.scalar(select(PayeePreference).where(PayeePreference.user_id == user_id, PayeePreference.payee == payee))
    if pref:
        pref.times_confirmed += 1 if pref.purpose == purpose else 0
        pref.purpose, pref.updated_at = purpose, now()
    else:
        db.add(PayeePreference(user_id=user_id, payee=payee, purpose=purpose))
    return {"ok": True, "message": f"Got it — I'll file {payee} as {purpose} from now on."}
