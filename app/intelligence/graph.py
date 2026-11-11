"""Relationship graph: who is connected to what, built from the briefcase (read-only, permission-scoped)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, Obligation, Participant, User


def for_user(db: Session, user_id: str) -> dict:
    nodes, edges = {f"user:{user_id}": {"id": f"user:{user_id}", "type": "you", "label": "You"}}, []
    case_ids = [p.case_id for p in db.scalars(select(Participant).where(Participant.party_id == user_id)).all()]
    for c in db.scalars(select(Case).where(Case.id.in_(case_ids))).all():
        nodes[f"case:{c.id}"] = {"id": f"case:{c.id}", "type": "purchase", "label": c.title[:40],
                                 "state": c.payment_state}
        edges.append({"from": f"user:{user_id}", "to": f"case:{c.id}", "label": "paid" if c.owner_id == user_id else "sold"})
        other = c.counterparty_id if c.owner_id == user_id else c.owner_id
        if other:
            u = db.get(User, other)
            nid = f"party:{other}"
            nodes.setdefault(nid, {"id": nid, "type": "business" if u and u.business_name else "person",
                                   "label": (u.business_name or u.name) if u else other})
            edges.append({"from": f"case:{c.id}", "to": nid, "label": "with"})
        else:
            nid = f"merchant:{c.merchant}"
            nodes.setdefault(nid, {"id": nid, "type": "merchant", "label": c.merchant})
            edges.append({"from": f"case:{c.id}", "to": nid, "label": "with"})
        for o in db.scalars(select(Obligation).where(Obligation.case_id == c.id, Obligation.status == "open")).all():
            oid = f"ob:{o.id}"
            nodes[oid] = {"id": oid, "type": "deadline", "label": o.kind.replace("_", " ")}
            edges.append({"from": f"case:{c.id}", "to": oid, "label": "due"})
    return {"nodes": list(nodes.values()), "edges": edges}
