"""Help-desk expert: find the right case from a free-text question, using least-privilege memory."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..intelligence.memory import MemoryItem, retrieve
from ..models import Case, Evidence, Obligation, Participant


def memory_for(db: Session, user_id: str) -> list[MemoryItem]:
    case_ids = [p.case_id for p in db.scalars(select(Participant).where(Participant.party_id == user_id)).all()]
    items: list[MemoryItem] = []
    for c in db.scalars(select(Case).where(Case.id.in_(case_ids))).all():
        items.append(MemoryItem("briefcase", f"{c.title} {c.merchant} {c.category} {c.channel} {c.payment_state}",
                                c.id, c.updated_at, user_id, {"case_id": c.id}))
    for e in db.scalars(select(Evidence).where(Evidence.case_id.in_(case_ids))).all():
        items.append(MemoryItem("briefcase", e.summary, e.case_id, e.created_at, user_id, {"case_id": e.case_id}))
    for o in db.scalars(select(Obligation).where(Obligation.owner_id == user_id)).all():
        items.append(MemoryItem("financial", o.title, o.case_id or o.id, o.due_at, user_id, {"case_id": o.case_id}))
    return items


def find_case(db: Session, user_id: str, question: str, expert: str = "helpdesk") -> Case | None:
    # 1) graph retrieval: text picks seed entities (a product, a seller), the graph walks to the purchase
    from ..intelligence import kg

    res = kg.build(db).retrieve(question, user_id, k_seeds=3, hops=1)
    for sd in res["seeds"]:
        if sd["id"].startswith("case:"):
            return db.get(Case, sd["id"][5:])
    g = kg.build(db)
    for sd in res["seeds"]:
        for f in g.neighborhood(sd["id"], user_id, hops=1):
            for n in (f.s, f.o):
                if n.startswith("case:"):
                    return db.get(Case, n[5:])
    # 2) fall back to plain memory retrieval
    hits = retrieve(memory_for(db, user_id), expert=expert, query=question, requester=user_id, k=5)
    for h in hits:
        cid = h.data.get("case_id")
        if cid:
            return db.get(Case, cid)
    latest = db.scalars(select(Case).join(Participant, Participant.case_id == Case.id)
                        .where(Participant.party_id == user_id).order_by(Case.updated_at.desc())).first()
    return latest


def list_cases(db: Session, user_id: str) -> list[dict]:
    rows = db.scalars(select(Case).join(Participant, Participant.case_id == Case.id)
                      .where(Participant.party_id == user_id).order_by(Case.created_at.desc())).all()
    return [{"id": c.id, "title": c.title, "merchant": c.merchant, "amount": c.amount, "currency": c.currency,
             "channel": c.channel, "purpose": c.purpose, "status": c.status, "payment_state": c.payment_state,
             "created_at": c.created_at.isoformat()} for c in rows]
