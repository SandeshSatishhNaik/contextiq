"""Payment service on top of the adapter: state tracking + self-healing capture/refund."""
from __future__ import annotations

import time

import httpx
from sqlalchemy.orm import Session

from .. import briefcase as bc
from ..config import settings
from ..models import Case, User
from .adapter import PayPalError, approve_link, capture_from_order, get_client

TRANSIENT = (httpx.TimeoutException, httpx.TransportError)


def create_order_for_case(db: Session, case: Case, items: list[dict], payee_email: str | None = None) -> dict:
    client = get_client()
    user = db.get(User, case.owner_id) if case.owner_id else None
    payer_email = user.paypal_email if (user and user.paypal_email) else None
    order = client.create_order(
        amount=case.amount, currency=case.currency, items=items, reference_id=case.id,
        description=case.title, request_id=f"order-{case.id}",
        return_url=f"{settings.public_base_url}/paypal/return?case={case.id}",
        cancel_url=f"{settings.public_base_url}/paypal/cancel?case={case.id}",
        payee_email=payee_email,
        payer_email=payer_email,
    )
    case.paypal_order_id = order["id"]
    bc.set_payment_state(db, case, "order_created", "paypal_api", {"order_id": order["id"], "status": order["status"]})
    bc.add_evidence(db, case, kind="paypal_order", source="paypal_api", provenance="verified",
                    summary=f"PayPal order {order['id']} created ({order['status']})",
                    content={"order_id": order["id"], "status": order["status"]})
    return {"order_id": order["id"], "approve_url": approve_link(order), "status": order["status"]}


def sync_order_state(db: Session, case: Case) -> dict:
    """Authoritative read from PayPal; updates the briefcase. Never trust a cache for this."""
    order = get_client().get_order(case.paypal_order_id)
    cap = capture_from_order(order)
    if cap and cap.get("status") in ("COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"):
        if case.paypal_capture_id != cap["id"]:
            case.paypal_capture_id = cap["id"]
            bc.set_payment_state(db, case, "captured", "paypal_api", {"capture_id": cap["id"]})
            bc.add_evidence(db, case, kind="paypal_capture", source="paypal_api", provenance="verified",
                            summary=f"Capture {cap['id']} {cap['status']} for {cap['amount']['value']} "
                                    f"{cap['amount']['currency_code']}", content=cap)
    elif cap and cap.get("status") == "PENDING":
        bc.set_payment_state(db, case, "capture_pending", "paypal_api", {"capture_id": cap["id"]})
    elif order["status"] == "APPROVED" and case.payment_state == "order_created":
        bc.set_payment_state(db, case, "buyer_approved", "paypal_api", {"order_id": order["id"]})
    return {"order_status": order["status"], "capture": cap}


def capture_safely(db: Session, case: Case, max_attempts: int = 3) -> dict:
    """Self-healing capture.

    The idempotency key is derived from the case, so every retry is the *same* request.
    After any timeout or dropped connection we read PayPal before doing anything else:
    if the capture already exists we record it and stop — no second charge.
    """
    client = get_client()
    request_id = f"capture-{case.id}"
    trace: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            order = client.capture_order(case.paypal_order_id, request_id=request_id)
            trace.append(f"attempt {attempt}: capture returned {order['status']}")
            sync_order_state(db, case)
            return {"ok": True, "capture_id": case.paypal_capture_id, "trace": trace, "healed": attempt > 1}
        except TRANSIENT as exc:
            trace.append(f"attempt {attempt}: {type(exc).__name__} — checking PayPal before any retry")
            bc.add_event(db, case, "payment_uncertain", "system", {"error": str(exc), "attempt": attempt})
            state = sync_order_state(db, case)
            if state["capture"] and state["capture"].get("status") == "COMPLETED":
                trace.append("PayPal shows the capture already COMPLETED → recorded it, no retry, no second charge")
                bc.add_event(db, case, "self_heal_resolved", "system",
                             {"resolution": "capture_already_completed", "capture_id": state["capture"]["id"]})
                return {"ok": True, "capture_id": case.paypal_capture_id, "trace": trace, "healed": True}
            trace.append(f"PayPal shows order {state['order_status']} and no capture → retry with the same request id")
            time.sleep(0.2 * 2 ** (attempt - 1))  # exponential backoff
        except PayPalError as exc:
            issues = [d.get("issue") for d in (exc.body or {}).get("details", [])] if isinstance(exc.body, dict) else []
            if "ORDER_ALREADY_CAPTURED" in issues:
                sync_order_state(db, case)
                trace.append("PayPal says already captured → recorded, no second charge")
                return {"ok": True, "capture_id": case.paypal_capture_id, "trace": trace, "healed": True}
            trace.append(f"attempt {attempt}: PayPal refused ({issues or exc.status})")
            bc.set_payment_state(db, case, "failed", "paypal_api", {"issues": issues, "status": exc.status})
            return {"ok": False, "error": issues or str(exc), "trace": trace}
    bc.add_event(db, case, "escalated_to_human", "system", {"reason": "capture unresolved after retries"})
    return {"ok": False, "error": "unresolved after retries; escalated", "trace": trace}


def add_tracking_for_case(db: Session, case: Case, tracking_number: str, carrier: str = "USPS") -> dict:
    """Seller ships: the tracking number goes to PayPal and comes back as verified evidence."""
    if not (case.paypal_order_id and case.paypal_capture_id):
        return {"ok": False, "error": "no verified PayPal capture on this case yet"}
    try:
        get_client().add_tracking(case.paypal_order_id, case.paypal_capture_id, tracking_number, carrier,
                                  request_id=f"track-{case.id}-{tracking_number}")
    except PayPalError as exc:
        return {"ok": False, "error": f"PayPal refused the tracking info ({exc.status})"}
    info = {"tracking_number": tracking_number, "carrier": carrier, "capture_id": case.paypal_capture_id}
    bc.add_evidence(db, case, kind="paypal_tracking", source="paypal_api", provenance="verified",
                    summary=f"Shipped: {carrier} {tracking_number}, registered with PayPal on capture "
                            f"{case.paypal_capture_id}", content=info)
    bc.add_event(db, case, "shipped", "paypal_api", info)
    return {"ok": True, **info}


def refund_safely(db: Session, case: Case, amount: float | None = None, reason: str = "") -> dict:
    if not case.paypal_capture_id:
        return {"ok": False, "error": "no verified capture on this case"}
    client = get_client()
    # Keyed per (case, amount): a retry of the same refund can never refund twice.
    request_id = f"refund-{case.id}-{amount if amount is not None else 'full'}"
    for attempt in range(1, 4):
        try:
            refund = client.refund_capture(case.paypal_capture_id, request_id=request_id, amount=amount,
                                           currency=case.currency, note=reason)
            full = amount is None or abs(amount - case.amount) < 0.005
            bc.set_payment_state(db, case, "refunded" if full else "partially_refunded", "paypal_api",
                                 {"refund_id": refund["id"], "amount": refund["amount"]})
            bc.add_evidence(db, case, kind="paypal_refund", source="paypal_api", provenance="verified",
                            summary=f"Refund {refund['id']} {refund['status']} for {refund['amount']['value']} "
                                    f"{refund['amount']['currency_code']}", content=refund)
            return {"ok": True, "refund": refund, "attempts": attempt}
        except TRANSIENT:
            time.sleep(0.2 * 2 ** (attempt - 1))  # exponential backoff; same request id → PayPal dedupes
        except PayPalError as exc:
            return {"ok": False, "error": exc.body}
    return {"ok": False, "error": "refund unresolved after retries"}
