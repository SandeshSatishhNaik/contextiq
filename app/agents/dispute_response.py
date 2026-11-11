"""Seller-side PayPal dispute responder.

PayPal tells us a buyer opened a case (webhook or a sync). The agent looks in the transaction briefcase
for what PayPal accepts as evidence, drafts the response, and recommends fight or accept. A person on the
seller side approves the exact draft (by its hash) before anything is sent; accepting a claim refunds money,
so it goes through the security gateway like any refund.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import briefcase as bc
from ..config import settings
from ..fmt import money
from ..models import Agreement, Case, CaseEvent, Evidence, PolicySnapshot
from ..paypal.adapter import PayPalError, get_client

INR = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
SNAD = "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED"
ACCEPT_BELOW = 10.0  # ponytail: flat threshold; a cost-of-fighting model belongs here if it matters


def _case_for(db: Session, dispute: dict) -> Case | None:
    for t in dispute.get("disputed_transactions") or []:
        cid = t.get("seller_transaction_id")
        if cid:
            case = db.scalar(select(Case).where(Case.paypal_capture_id == cid))
            if case:
                return case
    return None


def record(db: Session, dispute: dict) -> Case | None:
    """Store PayPal's view of a dispute on its case (verified: it came from PayPal). Idempotent per status."""
    case = _case_for(db, dispute)
    if not case:
        return None
    did, status = dispute["dispute_id"], dispute.get("status")
    if bc.add_event(db, case, f"paypal_dispute_{(status or 'unknown').lower()}", "paypal_api",
                    {"dispute_id": did, "reason": dispute.get("reason"), "status": status,
                     "outcome": (dispute.get("dispute_outcome") or {}).get("outcome_code")},
                    external_id=f"dispute:{did}:{status}:{(dispute.get('dispute_outcome') or {}).get('outcome_code')}"):
        bc.add_evidence(db, case, kind="paypal_dispute", source="paypal_api", provenance="verified",
                        summary=f"PayPal dispute {did}: {dispute.get('reason')} — {status}",
                        content={k: dispute.get(k) for k in ("dispute_id", "reason", "status", "dispute_amount",
                                                             "dispute_life_cycle_stage", "dispute_outcome",
                                                             "seller_response_due_date")})
    return case


def sync(db: Session) -> list[dict]:
    """Pull disputes from PayPal and attach each to its case (works without webhooks)."""
    client, out = get_client(), []
    for item in client.list_disputes().get("items", []):
        full = client.get_dispute(item["dispute_id"])
        case = record(db, full)
        out.append({"dispute_id": full["dispute_id"], "reason": full.get("reason"), "status": full.get("status"),
                    "case_id": case.id if case else None})
    return out


def current(db: Session, case: Case) -> dict | None:
    ev = db.scalar(select(Evidence).where(Evidence.case_id == case.id, Evidence.kind == "paypal_dispute")
                   .order_by(Evidence.created_at.desc()))
    return ev.content if ev else None


def draft(db: Session, case: Case) -> dict:
    """Evidence pack from the briefcase, in PayPal's provide-evidence shape, plus a recommendation."""
    d = current(db, case)
    if not d:
        return {"ok": False, "error": "PayPal has not reported a dispute on this payment"}
    tracking = db.scalar(select(Evidence).where(Evidence.case_id == case.id, Evidence.kind == "paypal_tracking")
                         .order_by(Evidence.created_at.desc()))
    delivered = db.scalar(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.type == "delivered"))
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    pol = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case.id))

    facts, notes, evidences = [], [], []
    facts.append(f"PayPal capture {case.paypal_capture_id} for {money(case.amount, case.currency)}")
    if ag:
        facts.append(f"agreement fingerprint {ag.signed_hash[:16]}… for {money(ag.amount, ag.currency)} to {ag.payee}")
        notes.append(f"Buyer approved exactly: {', '.join(i.get('name', '') for i in ag.items)} for "
                     f"{money(ag.amount, ag.currency)} (SHA-256 {ag.signed_hash}).")
    if pol:
        facts.append(f"store terms saved {pol.captured_at:%Y-%m-%d} before payment")
        terms = pol.extracted or {}
        notes.append(f"Store terms shown before purchase ({pol.url}): returns {terms.get('return_window_days', '?')} days "
                     f"from {terms.get('starts_from', '?')}.")
    if tracking:
        t = tracking.content
        facts.append(f"{t['carrier']} tracking {t['tracking_number']} registered with PayPal")
        evidences.append({"evidence_type": "PROOF_OF_FULFILLMENT",
                          "evidence_info": {"tracking_info": [{"carrier_name": t["carrier"],
                                                               "tracking_number": t["tracking_number"]}]},
                          "notes": " ".join(notes)[:2000]})
    if delivered:
        facts.append(f"delivery recorded {delivered.occurred_at:%Y-%m-%d} (source: {delivered.source})")
    if not evidences and notes:
        evidences.append({"evidence_type": "OTHER", "notes": " ".join(notes)[:2000]})

    reason = d.get("reason")
    strong = (reason == INR and tracking is not None) or (reason == SNAD and ag is not None and pol is not None)
    if case.amount < ACCEPT_BELOW:
        rec, why = "accept", f"under {money(ACCEPT_BELOW, case.currency)}: refunding costs less than fighting"
    elif strong:
        rec, why = "fight", ("shipment tracking is on file with PayPal" if reason == INR
                             else "the buyer approved these exact terms and items before paying")
    else:
        rec, why = "accept", "the briefcase lacks the evidence PayPal needs for this reason"
    payload = {"dispute_id": d["dispute_id"], "evidences": evidences}
    return {"ok": True, "dispute": d, "recommendation": rec, "why": why, "facts": facts,
            "payload": payload, "draft_hash": bc.content_hash(payload)}


def submit(db: Session, case: Case, draft_hash: str) -> dict:
    """Sends the evidence the seller approved. The hash must match the current draft, so what was
    reviewed is exactly what goes to PayPal."""
    dr = draft(db, case)
    if not dr.get("ok"):
        return dr
    if not dr["payload"]["evidences"]:
        return {"ok": False, "error": "nothing in the briefcase to send as evidence"}
    if draft_hash != dr["draft_hash"]:
        return {"ok": False, "error": "the draft changed since you reviewed it; review it again"}
    did = dr["dispute"]["dispute_id"]
    try:
        get_client().provide_evidence(did, dr["payload"]["evidences"])
    except PayPalError as exc:
        return {"ok": False, "error": f"PayPal did not accept the evidence ({exc.status}): {exc.body}"[:400]}
    bc.add_event(db, case, "dispute_evidence_submitted", "seller", {"dispute_id": did, "draft_hash": draft_hash})
    record(db, get_client().get_dispute(did))
    return {"ok": True, "dispute_id": did, "submitted": [e["evidence_type"] for e in dr["payload"]["evidences"]]}


def accept(db: Session, case: Case, note: str) -> dict:
    """Seller accepts the claim: PayPal refunds the buyer. Caller must have passed the gateway."""
    d = current(db, case)
    if not d:
        return {"ok": False, "error": "no PayPal dispute on this payment"}
    try:
        get_client().accept_claim(d["dispute_id"], note or "Seller accepts the claim.")
    except PayPalError as exc:
        return {"ok": False, "error": f"PayPal refused ({exc.status})"}
    record(db, get_client().get_dispute(d["dispute_id"]))
    bc.set_payment_state(db, case, "refunded", "paypal_api", {"via": "dispute_accept", "dispute_id": d["dispute_id"]})
    return {"ok": True, "dispute_id": d["dispute_id"]}


def sandbox_decide(db: Session, case: Case, outcome: str = "SELLER_FAVOR") -> dict:
    """Sandbox only: ask PayPal's sandbox to decide the case (stands in for PayPal's review team)."""
    if settings.paypal_env == "live":
        return {"ok": False, "error": "only available in sandbox"}
    d = current(db, case)
    if not d:
        return {"ok": False, "error": "no PayPal dispute on this payment"}
    try:
        get_client().adjudicate(d["dispute_id"], outcome)
    except PayPalError as exc:
        return {"ok": False, "error": f"PayPal sandbox refused ({exc.status}): {exc.body}"[:400]}
    full = get_client().get_dispute(d["dispute_id"])
    record(db, full)
    return {"ok": True, "status": full.get("status"), "outcome": (full.get("dispute_outcome") or {}).get("outcome_code")}
