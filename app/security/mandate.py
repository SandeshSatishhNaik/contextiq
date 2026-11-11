"""Signed spending mandates (AP2-shaped, our implementation).

At checkout the buyer's approval becomes an Ed25519-signed mandate: who pays whom, the most that may be
charged, which exact items (by the agreement fingerprint), and until when. The PayPal order carries the
mandate's hash in `custom_id`, so PayPal's own record points back to it. Before any capture the mandate is
checked again and the payment fails closed if it is missing, altered, expired, revoked, over the cap, to a
different payee, or for different items. An agent (or a prompt-injected page) cannot talk its way past it.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import briefcase as bc
from ..models import Agreement, Case, CaseEvent, Evidence
from .crypto import TokenError, sign_message, verify_message

TTL_SECONDS = 7 * 24 * 3600  # a checkout mandate is valid for a week


def mandate_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Session, case: Case, agreement: Agreement, payer: str) -> dict:
    payload = {"typ": "contextiq.mandate/1", "case": case.id, "payer": payer, "payee": agreement.payee,
               "max_amount": round(agreement.amount, 2), "currency": agreement.currency,
               "items_fp": agreement.signed_hash, "agent": "contextiq"}
    token = sign_message(payload, ttl=TTL_SECONDS)
    h = mandate_hash(token)
    bc.add_evidence(db, case, kind="spending_mandate", source="contextiq", provenance="verified",
                    summary=f"Signed spending mandate: up to {agreement.currency} {agreement.amount:.2f} to "
                            f"{agreement.payee} for these exact items (#{h[:8]})",
                    content={"token": token, "hash": h, **payload})
    return {"token": token, "hash": h}


def current(db: Session, case: Case) -> Evidence | None:
    return db.scalar(select(Evidence).where(Evidence.case_id == case.id, Evidence.kind == "spending_mandate")
                     .order_by(Evidence.created_at.desc()))


def revoke(db: Session, case: Case, by: str) -> dict:
    ev = current(db, case)
    if not ev:
        return {"ok": False, "error": "no mandate on this purchase"}
    bc.add_event(db, case, "mandate_revoked", by, {"hash": ev.content["hash"]})
    return {"ok": True, "hash": ev.content["hash"]}


def verify(db: Session, case: Case, *, amount: float | None = None, payee: str | None = None,
           token: str | None = None) -> tuple[bool, str]:
    """Checks a charge of `amount` to `payee` against the signed mandate. Returns (ok, reason)."""
    ev = current(db, case)
    if not ev:
        return False, "no signed spending mandate for this purchase"
    token = token or ev.content["token"]
    try:
        body = verify_message(db, token, consume=False)
    except TokenError as exc:
        return False, f"mandate rejected: {exc}"
    if body.get("typ") != "contextiq.mandate/1" or body.get("case") != case.id:
        return False, "mandate is for a different purchase"
    if db.scalar(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.type == "mandate_revoked")):
        return False, "the buyer revoked this mandate"
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    if not ag or ag.signed_hash != body["items_fp"]:
        return False, "the items no longer match what the buyer approved"
    if body["payer"] != case.owner_id:
        return False, "mandate was signed for a different payer"
    if (payee or ag.payee) != body["payee"]:
        return False, f"payee {payee!r} is not the payee the buyer approved ({body['payee']})"
    charge = case.amount if amount is None else amount
    if round(charge, 2) > body["max_amount"] + 1e-9:
        return False, (f"{body['currency']} {charge:.2f} is over the signed limit of "
                       f"{body['currency']} {body['max_amount']:.2f}")
    return True, f"within the signed mandate #{mandate_hash(token)[:8]}"


def overspend_test(db: Session, case: Case) -> dict:
    """Demo: a prompt-injected agent tries to raise the charge and redirect it. The mandate stops both."""
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    attempts = [
        ("Hidden text on the store page told the agent to add a 'priority fee'", round(case.amount * 1.4, 2), None),
        ("Same page told it to pay a different account", case.amount, "Quick-Refund Services Ltd"),
    ]
    out = []
    for story, amt, payee in attempts:
        ok, why = verify(db, case, amount=amt, payee=payee)
        out.append({"attempt": story, "amount": amt, "payee": payee or (ag.payee if ag else None),
                    "allowed": ok, "reason": why})
        bc.add_event(db, case, "mandate_blocked" if not ok else "mandate_checked", "security",
                     {"attempt": story, "amount": amt, "payee": payee, "reason": why})
    return {"attempts": out, "blocked": sum(not a["allowed"] for a in out)}
