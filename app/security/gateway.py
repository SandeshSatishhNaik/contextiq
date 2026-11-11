"""Security policy gateway — policy as code, independent of any AI output.

AI agents may *propose* actions. Only this gateway turns a proposal into a permitted call.
Order of checks: identity → permission → explicit approval of the exact amount/payee →
risk decision → limits (step-up) → idempotency → audit.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agreement, Approval, AuditLog, Case, LedgerEntry, Participant, SecurityEvent
from .crypto import hmac_token

MONEY_ACTIONS = {"capture", "refund", "pay_invoice"}
ACTION_ROLE = {"capture": "buyer", "pay_invoice": "buyer", "refund": "seller", "request_refund": "buyer",
               "share_case": None, "view_case": None}


@dataclass
class Verdict:
    decision: str  # allow | step_up | review | deny
    reasons: list[str] = field(default_factory=list)
    step_up_code: str | None = None  # demo only: in production this goes to an independent channel

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


def issue_approval(db: Session, *, user_id: str, case: Case, action: str) -> Approval:
    """User explicitly approves THIS amount to THIS payee for THIS action."""
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    payee = ag.payee if ag else case.merchant
    token = hmac_token(user_id, case.id, action, f"{case.amount:.2f}", payee, secrets.token_hex(4))
    ap = Approval(token=token, user_id=user_id, case_id=case.id, action=action, amount=case.amount, payee=payee,
                  expires_at=datetime.now(UTC) + timedelta(seconds=settings.approval_ttl_seconds))
    db.add(ap)
    db.flush()
    return ap


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def check(db: Session, *, actor: str, action: str, case: Case, approval_token: str | None = None,
          amount: float | None = None, risk: dict | None = None, session_ok: bool = True) -> Verdict:
    reasons: list[str] = []
    amount = case.amount if amount is None else amount

    if not session_ok:
        return _audit(db, actor, action, case, Verdict("deny", ["no authenticated session"]))

    part = db.scalar(select(Participant).where(Participant.case_id == case.id, Participant.party_id == actor))
    needed_role = ACTION_ROLE.get(action)
    if not part or (needed_role and part.role != needed_role):
        return _audit(db, actor, action, case, Verdict("deny", [f"{actor} has no {needed_role or 'access'} "
                                                                f"permission on this case"]))

    approval = None
    if action in MONEY_ACTIONS:
        approval = db.get(Approval, approval_token) if approval_token else None
        if not approval or approval.used or approval.case_id != case.id or approval.action != action:
            return _audit(db, actor, action, case, Verdict("deny", ["no valid explicit approval for this action"]))
        if _aware(approval.expires_at) < datetime.now(UTC):
            return _audit(db, actor, action, case, Verdict("deny", ["approval expired"]))
        if abs(approval.amount - amount) > 0.005 and action != "refund":
            return _audit(db, actor, action, case, Verdict("deny", ["amount differs from the approved amount"]))
        ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
        if ag and approval.payee != ag.payee:
            return _audit(db, actor, action, case, Verdict("deny", ["payee differs from the agreed payee"]))

    if risk:
        rd = risk.get("decision", "allow")
        if rd == "block":
            return _audit(db, actor, action, case, Verdict("deny", ["fraud decision: block"] + risk.get("reasons", [])))
        if rd == "review":
            return _audit(db, actor, action, case, Verdict("review", ["held for human review"] + risk.get("reasons", [])))
        if rd == "step_up":
            reasons.append("fraud model requested additional verification")

    if action in MONEY_ACTIONS and approval is not None:
        new_payee = not db.scalar(select(LedgerEntry).where(LedgerEntry.user_id == actor,
                                                            LedgerEntry.payee == approval.payee).limit(1))
        if amount >= settings.step_up_amount:
            reasons.append(f"amount ≥ {settings.step_up_amount:.0f} needs step-up")
        if new_payee and amount >= settings.new_payee_step_up_amount:
            reasons.append(f"new payee and amount ≥ {settings.new_payee_step_up_amount:.0f} needs step-up")
        if reasons and not approval.step_up_passed:
            if not approval.step_up_code:
                approval.step_up_code = f"{secrets.randbelow(10**6):06d}"
            return _audit(db, actor, action, case, Verdict("step_up", reasons, step_up_code=approval.step_up_code))
        approval.used = True
        if reasons:
            reasons = ["step-up passed"] + reasons

    return _audit(db, actor, action, case, Verdict("allow", reasons or ["all checks passed"]))


def pass_step_up(db: Session, approval_token: str, code: str) -> bool:
    ap = db.get(Approval, approval_token)
    if ap and ap.step_up_code and secrets.compare_digest(ap.step_up_code, code):
        ap.step_up_passed = True
        return True
    db.add(SecurityEvent(user_id=ap.user_id if ap else None, kind="step_up_failed", severity="warning",
                         detail={"approval": approval_token}))
    return False


def _audit(db: Session, actor: str, action: str, case: Case, verdict: Verdict) -> Verdict:
    db.add(AuditLog(actor=actor, action=action, case_id=case.id,
                    request={"amount": case.amount, "payee": case.merchant},
                    verdict=verdict.decision, reasons=verdict.reasons))
    if verdict.decision in ("deny", "review"):
        db.add(SecurityEvent(user_id=actor, kind=f"gateway_{verdict.decision}", severity="warning",
                             detail={"action": action, "case": case.id, "reasons": verdict.reasons}))
    db.flush()
    return verdict
