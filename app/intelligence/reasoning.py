"""Unified reasoning services shared by all experts. Each expert supplies its own evidence,
alternatives and constraints; these functions stay domain-neutral.

- uncertainty(): how much of the required evidence exists, weighted by provenance
- counterfactual(): simulate each alternative action on a state and compare outcomes
- causal_chain(): explain *why* a payment situation exists from the event timeline
- temporal(): deadline status with days remaining
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ..briefcase import PROVENANCE_WEIGHT


@dataclass
class Fact:
    name: str
    value: object
    provenance: str  # verified | claimed | inferred
    evidence_id: str | None = None


def uncertainty(required: list[str], facts: list[Fact]) -> dict:
    have = {f.name: f for f in facts}
    present = [n for n in required if n in have]
    missing = [n for n in required if n not in have]
    coverage = len(present) / len(required) if required else 1.0
    strength = (sum(PROVENANCE_WEIGHT[have[n].provenance] for n in present) / len(required)) if required else 1.0
    level = "high" if strength >= 0.85 else "medium" if strength >= 0.5 else "low"
    return {"coverage": round(coverage, 2), "confidence": round(strength, 2), "level": level,
            "missing": missing, "weak": [n for n in present if have[n].provenance != "verified"]}


def counterfactual(state: dict, actions: dict[str, Callable[[dict], dict]]) -> dict[str, dict]:
    """Run each action on a copy of the state. Actions return outcome metrics (no side effects)."""
    return {name: fn(dict(state)) for name, fn in actions.items()}


def causal_chain(case: dict, events: list[dict], agreement: dict | None, counterparty_view: dict | None = None) -> dict:
    """Rule-based root-cause analysis for 'X says payment wasn't received'-type questions."""
    types = [e["type"] for e in events]
    chain, verdict = [], "unknown"
    if "payment_captured" in types or case.get("paypal_capture_id"):
        chain.append("PayPal shows a completed capture for this order (verified).")
        if any(t.startswith("payment_refunded") or t == "payment_partially_refunded" for t in types):
            chain.append("A refund was later issued, so part or all of the money went back.")
            verdict = "refunded"
        else:
            verdict = "paid"
            if agreement and counterparty_view and counterparty_view.get("expected_payee") not in (None, agreement["payee"]):
                chain.append("The payee on the agreement differs from the account the supplier is checking.")
                verdict = "paid_to_different_account"
            else:
                chain.append("Funds reached the payee's PayPal balance; a bank withdrawal is a separate step "
                             "the payee controls, so 'not in my bank' can still be true.")
    elif "payment_capture_pending" in types:
        chain.append("The capture is PENDING at PayPal (held, e.g. for review); money has not settled yet.")
        verdict = "pending"
    elif "payment_uncertain" in types:
        chain.append("A connection problem happened during payment; PayPal shows no completed capture.")
        verdict = "not_paid"
    elif "payment_buyer_approved" in types:
        chain.append("The buyer approved the order, but it was never captured.")
        verdict = "approved_not_captured"
    elif "payment_order_created" in types:
        chain.append("An order was created but the buyer never approved it.")
        verdict = "not_paid"
    else:
        chain.append("No PayPal order exists for this case yet.")
        verdict = "not_started"
    return {"verdict": verdict, "chain": chain}


def temporal(due_at: datetime, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    due = due_at if due_at.tzinfo else due_at.replace(tzinfo=UTC)
    days = (due - now).total_seconds() / 86400
    return {"days_left": round(days, 1), "status": "expired" if days < 0 else "closing" if days <= 2 else "open"}
