"""Two-sided dispute analysis and obligation checklists.

Buyer and seller each make claims (stored as 'claimed' evidence). The analysis lines those claims up against
what is verified (PayPal events, signed agreements, delivery records) and sorts every point into
agreed / disputed / unknown — instead of picking a side.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import briefcase as bc
from ..fmt import money
from ..models import Agreement, Case, CaseEvent, Evidence, Participant

TOPICS = ("paid", "delivered", "amount_correct", "item_ok")


def add_claim(db: Session, case: Case, party_id: str, topic: str, value: bool, note: str = "") -> dict:
    part = db.scalar(select(Participant).where(Participant.case_id == case.id, Participant.party_id == party_id))
    if not part or topic not in TOPICS:
        return {"ok": False, "error": "not a participant or unknown topic"}
    bc.add_evidence(db, case, kind=f"claim_{topic}", source=part.role, provenance="claimed",
                    summary=f"The {part.role} says {topic.replace('_', ' ')}: {'yes' if value else 'no'}. {note}".strip(),
                    content={"topic": topic, "value": value, "party": party_id, "role": part.role})
    bc.add_event(db, case, "claim_added", part.role, {"topic": topic, "value": value})
    return {"ok": True}


def compare(db: Session, case: Case) -> dict:
    events = {e.type for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id)).all()}
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    claims = db.scalars(select(Evidence).where(Evidence.case_id == case.id, Evidence.kind.like("claim_%"))).all()
    verified = {
        "paid": True if case.paypal_capture_id and case.payment_state in ("captured", "partially_refunded") else
                (False if case.payment_state in ("order_created", "failed", "intent_recorded") else None),
        "delivered": True if "delivered" in events else None,
        "amount_correct": True if ag and abs(ag.amount - case.amount) < 0.005 else None,
        "item_ok": None,
    }
    rows = []
    for topic in TOPICS:
        said = {c.content["role"]: c.content["value"] for c in claims if c.content.get("topic") == topic}
        v = verified[topic]
        if v is not None:
            status = "agreed" if all(x == v for x in said.values()) else "settled by evidence"
            basis = "PayPal / signed records"
        elif len(set(said.values())) > 1:
            status, basis = "disputed", "the two sides disagree and nothing verified settles it"
        elif said:
            status, basis = "claimed by one side", "only a claim, not verified"
        else:
            status, basis = "unknown", "no record yet"
        rows.append({"topic": topic.replace("_", " "), "buyer_says": said.get("buyer"), "seller_says": said.get("seller"),
                     "verified": v, "status": status, "basis": basis})
    open_points = [r for r in rows if r["status"] in ("disputed", "claimed by one side", "unknown")]
    if any(r["status"] == "disputed" for r in rows):
        rec = "Ask for the missing proof (e.g. a delivery confirmation or photos). If it stays disputed, open a PayPal case."
    elif open_points:
        rec = "Nothing contradicts so far. Collect the missing records below before anyone pays or refunds."
    else:
        rec = "Everything is agreed or settled by verified records."
    return {"case_id": case.id, "amount": money(case.amount, case.currency), "points": rows, "recommendation": rec}


def checklist(db: Session, case: Case) -> list[dict]:
    """Items tick themselves only when a verified event arrives — never on a claim."""
    events = {e.type: e for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id)).all()}
    items = [("Agreement recorded", "intent_recorded" in events),
             ("Payment approved by you on PayPal", any(k in events for k in ("payment_buyer_approved", "payment_captured"))),
             ("Payment captured by PayPal", "payment_captured" in events)]
    if case.channel in ("online", "invoice"):
        items.append(("Delivery confirmed", "delivered" in events))
    if any(k.startswith("payment_refunded") or k == "payment_partially_refunded" for k in events):
        items.append(("Refund completed by PayPal", True))
    return [{"item": i, "done": bool(d)} for i, d in items]
