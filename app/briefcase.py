"""Briefcase service: create cases, append events, attach evidence, build compact summaries."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Agreement,
    Case,
    CaseEvent,
    Evidence,
    Obligation,
    Participant,
    PolicySnapshot,
    now,
)

PROVENANCE_WEIGHT = {"verified": 1.0, "claimed": 0.5, "inferred": 0.3}


def content_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def create_case(db: Session, *, owner_id: str, title: str, merchant: str, amount: float, currency: str,
                channel: str = "online", purpose: str = "personal", category: str = "general",
                counterparty_id: str | None = None) -> Case:
    case = Case(owner_id=owner_id, title=title, merchant=merchant, amount=round(amount, 2), currency=currency,
                channel=channel, purpose=purpose, category=category, counterparty_id=counterparty_id,
                status="draft")
    db.add(case)
    db.flush()
    db.add(Participant(case_id=case.id, party_id=owner_id, role="buyer"))
    if counterparty_id:
        db.add(Participant(case_id=case.id, party_id=counterparty_id, role="seller"))
    add_event(db, case, "case_created", "system", {"channel": channel, "purpose": purpose, "amount": amount})
    return case


def add_event(db: Session, case: Case, type_: str, source: str, payload: dict | None = None,
              external_id: str | None = None) -> CaseEvent | None:
    """Append-only. A repeated external_id (e.g. a PayPal webhook delivered twice) is dropped."""
    if external_id:
        exists = db.scalar(select(CaseEvent).where(CaseEvent.external_id == external_id))
        if exists:
            return None
    ev = CaseEvent(case_id=case.id, type=type_, source=source, payload=payload or {}, external_id=external_id)
    db.add(ev)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    case.rev += 1
    case.updated_at = now()
    return ev


def add_evidence(db: Session, case: Case, *, kind: str, source: str, provenance: str, summary: str,
                 content: dict | None = None, cites: list[str] | None = None, visible_to: str = "both") -> Evidence:
    assert provenance in PROVENANCE_WEIGHT, provenance
    if provenance == "inferred" and not cites:
        raise ValueError("an inferred finding must cite the evidence it rests on")
    content = content or {}
    ev = Evidence(case_id=case.id, kind=kind, source=source, provenance=provenance, summary=summary,
                  content=content, content_hash=content_hash(content), cites=cites or [], visible_to=visible_to)
    db.add(ev)
    db.flush()
    return ev


def record_agreement(db: Session, case: Case, *, items: list[dict], amount: float, currency: str, payee: str,
                     terms: dict, approved_by: str | None = None) -> Agreement:
    """Proof of intent: exactly what the user agreed to pay for, hashed so it cannot drift."""
    body = {"items": items, "amount": round(amount, 2), "currency": currency, "payee": payee, "terms": terms}
    ag = Agreement(case_id=case.id, items=items, amount=round(amount, 2), currency=currency, payee=payee,
                   terms=terms, signed_hash=content_hash(body), approved_by=approved_by,
                   approved_at=now() if approved_by else None)
    db.add(ag)
    db.flush()
    add_evidence(db, case, kind="agreement", source="contextiq", provenance="verified",
                 summary=f"Agreed to pay {currency} {amount:.2f} to {payee} for {len(items)} item(s)",
                 content=body)
    add_event(db, case, "intent_recorded", "user", {"agreement_id": ag.id, "hash": ag.signed_hash})
    return ag


def set_payment_state(db: Session, case: Case, state: str, source: str, payload: dict | None = None,
                      external_id: str | None = None) -> None:
    case.payment_state = state
    if state == "captured" and case.status in ("draft", "active"):
        case.status = "monitoring"
    elif state in ("order_created", "buyer_approved"):
        case.status = "active"
    add_event(db, case, f"payment_{state}", source, payload or {}, external_id=external_id)


def view_case(db: Session, case_id: str, party_id: str) -> dict | None:
    """Permission-scoped view: each side sees only its fields (the 'attention mask' for humans)."""
    case = db.get(Case, case_id)
    if not case:
        return None
    part = db.scalar(select(Participant).where(Participant.case_id == case_id, Participant.party_id == party_id))
    if not part:
        return None
    role = part.role
    evidence = db.scalars(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.created_at)).all()
    events = db.scalars(select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.occurred_at)).all()
    obligations = db.scalars(select(Obligation).where(Obligation.case_id == case_id)).all()
    agreement = db.scalar(select(Agreement).where(Agreement.case_id == case_id))
    policy = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case_id))
    hidden_event_types = {"budget_check"} if role == "seller" else set()
    return {
        "role": role,
        "case": {k: getattr(case, k) for k in ("id", "title", "merchant", "channel", "purpose", "category",
                                                 "amount", "currency", "status", "payment_state",
                                                 "paypal_order_id", "paypal_capture_id", "rev")}
        | {"created_at": case.created_at.isoformat()},
        "agreement": None if not agreement else {"items": agreement.items, "amount": agreement.amount,
                                                  "currency": agreement.currency, "payee": agreement.payee,
                                                  "terms": agreement.terms, "hash": agreement.signed_hash},
        "policy": None if not policy else {"merchant": policy.merchant, "url": policy.url,
                                            "extracted": policy.extracted,
                                            "captured_at": policy.captured_at.isoformat()},
        "events": [{"id": e.id, "type": e.type, "source": e.source, "at": e.occurred_at.isoformat(),
                    "payload": e.payload} for e in events if e.type not in hidden_event_types],
        "evidence": [{"id": e.id, "kind": e.kind, "provenance": e.provenance, "source": e.source,
                      "summary": e.summary, "cites": e.cites} for e in evidence
                     if e.visible_to in ("both", role)],
        "obligations": [{"id": o.id, "kind": o.kind, "title": o.title, "due_at": o.due_at.isoformat(),
                         "status": o.status, "amount": o.amount} for o in obligations],
    }


def case_summary(db: Session, case: Case, max_events: int = 5) -> dict:
    """Compact JSON (~200 tokens) handed to reasoning — never the raw event log."""
    events = db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id)
                        .order_by(CaseEvent.occurred_at.desc()).limit(max_events)).all()
    obligations = db.scalars(select(Obligation).where(Obligation.case_id == case.id,
                                                      Obligation.status == "open")).all()
    evidence = db.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
    return {
        "case_id": case.id, "title": case.title, "merchant": case.merchant, "amount": case.amount,
        "currency": case.currency, "channel": case.channel, "payment_state": case.payment_state,
        "status": case.status,
        "open_obligations": [{"kind": o.kind, "due": o.due_at.date().isoformat()} for o in obligations],
        "recent_events": [e.type for e in events],
        "evidence": {p: sum(1 for e in evidence if e.provenance == p) for p in PROVENANCE_WEIGHT},
    }


def maybe_archive(db: Session, case: Case, at: datetime | None = None) -> bool:
    """Archive only when every obligation is closed — one passed deadline is not enough."""
    at = at or datetime.now(UTC)
    open_obs = db.scalars(select(Obligation).where(Obligation.case_id == case.id, Obligation.status == "open")).all()
    if open_obs:
        return False
    if case.payment_state in ("captured", "refunded", "partially_refunded", "voided"):
        case.status = "archived"
        add_event(db, case, "case_archived", "system", {})
        return True
    return False
