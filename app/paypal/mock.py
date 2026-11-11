"""Offline PayPal: an httpx transport returning PayPal-shaped REST responses.

Used only when PAYPAL_ENV=mock. It honours PayPal-Request-Id idempotency and can
inject a failure *after* a capture is committed (to exercise self-healing), which is
exactly the dangerous case: the money moved but the client never heard back.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime

import httpx

_lock = threading.Lock()
ORDERS: dict[str, dict] = {}
CAPTURES: dict[str, dict] = {}
REFUNDS: dict[str, dict] = {}
INVOICES: dict[str, dict] = {}
IDEMPOTENT: dict[tuple[str, str], tuple[int, dict]] = {}
FAULTS: dict[str, int] = {}  # "capture_timeout_after_commit" -> remaining count
EVENTS: list[dict] = []  # webhook events the mock "sends"
CALLS: list[str] = []


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:15].upper()


from ..config import DATA_DIR

_STORE = DATA_DIR / "mock_paypal.json"


def _save() -> None:
    _STORE.write_text(json.dumps({"orders": ORDERS, "captures": CAPTURES, "refunds": REFUNDS, "invoices": INVOICES,
                                  "idem": {f"{k[0]}|{k[1]}": v for k, v in IDEMPOTENT.items()}}))


def _load() -> None:
    if not _STORE.exists():
        return
    try:
        d = json.loads(_STORE.read_text())
    except ValueError:
        return
    ORDERS.update(d["orders"]); CAPTURES.update(d["captures"]); REFUNDS.update(d["refunds"]); INVOICES.update(d["invoices"])
    IDEMPOTENT.update({tuple(k.split("|", 1)): tuple(v) for k, v in d["idem"].items()})


def reset() -> None:
    with _lock:
        for d in (ORDERS, CAPTURES, REFUNDS, INVOICES, IDEMPOTENT, FAULTS):
            d.clear()
        EVENTS.clear()
        CALLS.clear()


def inject_fault(name: str, times: int = 1) -> None:
    FAULTS[name] = FAULTS.get(name, 0) + times


def approve(order_id: str) -> dict:
    """Simulates the buyer approving the order on PayPal's page."""
    with _lock:
        order = ORDERS[order_id]
        if order["status"] in ("CREATED", "PAYER_ACTION_REQUIRED"):
            order["status"] = "APPROVED"
            order["payer"] = {"email_address": "buyer@example.com", "payer_id": "MOCKBUYER01"}
            _save()
        return order


def _event(event_type: str, resource: dict) -> None:
    EVENTS.append({"id": _id("WH-"), "event_type": event_type, "create_time": _now(), "resource": resource})


def _json(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode(), headers={"Content-Type": "application/json"})


def _handler(request: httpx.Request) -> httpx.Response:
    path, method = request.url.path, request.method
    CALLS.append(f"{method} {path}")
    if path == "/v1/oauth2/token":
        return _json(200, {"access_token": "MOCK-TOKEN", "token_type": "Bearer", "expires_in": 32400})
    if not request.headers.get("authorization", "").startswith("Bearer "):
        return _json(401, {"error": "invalid_token"})

    req_id = request.headers.get("paypal-request-id")
    if req_id and method == "POST":
        key = (path, req_id)
        if key in IDEMPOTENT:
            status, body = IDEMPOTENT[key]
            return _json(status, body)

    body = json.loads(request.content or b"{}") if request.content else {}
    with _lock:
        status, payload = _route(method, path, body)
        if req_id and method == "POST" and status < 500:
            IDEMPOTENT[(path, req_id)] = (status, payload)
        if method == "POST":
            _save()

    if path.endswith("/capture") and status == 201 and FAULTS.get("capture_timeout_after_commit", 0) > 0:
        FAULTS["capture_timeout_after_commit"] -= 1
        raise httpx.ReadTimeout("simulated: connection dropped after PayPal committed the capture", request=request)
    return _json(status, payload)


def _route(method: str, path: str, body: dict) -> tuple[int, dict]:
    parts = [p for p in path.split("/") if p]
    # Orders v2
    if parts[:3] == ["v2", "checkout", "orders"]:
        if method == "POST" and len(parts) == 3:
            oid = _id("ORD")
            unit = body["purchase_units"][0]
            order = {
                "id": oid, "intent": body.get("intent", "CAPTURE"), "status": "PAYER_ACTION_REQUIRED",
                "create_time": _now(),
                "purchase_units": [{**unit, "payments": {"captures": []}}],
                "links": [
                    {"href": f"https://mock.paypal.local/checkoutnow?token={oid}", "rel": "payer-action", "method": "GET"},
                    {"href": f"https://mock.paypal.local/v2/checkout/orders/{oid}", "rel": "self", "method": "GET"},
                ],
            }
            ORDERS[oid] = order
            return 201, order
        if len(parts) >= 4:
            oid = parts[3]
            order = ORDERS.get(oid)
            if not order:
                return 404, {"name": "RESOURCE_NOT_FOUND", "message": "order not found"}
            if method == "GET" and len(parts) == 4:
                return 200, order
            if method == "POST" and len(parts) == 5 and parts[4] == "track":
                unit = order["purchase_units"][0]
                if not any(c["id"] == body.get("capture_id") for c in unit["payments"]["captures"]):
                    return 422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "CAPTURE_ID_NOT_FOUND"}]}
                tracker = {"id": f"{body['capture_id']}-{body['tracking_number']}", "status": "SHIPPED",
                           "number": body["tracking_number"], "carrier": body["carrier"], "create_time": _now()}
                unit.setdefault("shipping", {}).setdefault("trackers", []).append(tracker)
                return 201, order
            if method == "POST" and len(parts) == 5 and parts[4] == "capture":
                if order["status"] == "COMPLETED":
                    return 422, {"name": "UNPROCESSABLE_ENTITY",
                                 "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]}
                if order["status"] != "APPROVED":
                    return 422, {"name": "UNPROCESSABLE_ENTITY",
                                 "details": [{"issue": "ORDER_NOT_APPROVED"}]}
                unit = order["purchase_units"][0]
                cid = _id("CAP")
                capture = {"id": cid, "status": "COMPLETED", "amount": unit["amount"] | {},
                           "final_capture": True, "create_time": _now(),
                           "supplementary_data": {"related_ids": {"order_id": oid}}}
                capture["amount"] = {"currency_code": unit["amount"]["currency_code"],
                                     "value": unit["amount"]["value"]}
                CAPTURES[cid] = capture
                unit["payments"]["captures"].append(capture)
                order["status"] = "COMPLETED"
                _event("PAYMENT.CAPTURE.COMPLETED", capture)
                return 201, order
    # Payments v2
    if parts[:3] == ["v2", "payments", "captures"] and method == "POST" and parts[-1] == "refund":
        cid = parts[3]
        cap = CAPTURES.get(cid)
        if not cap:
            return 404, {"name": "RESOURCE_NOT_FOUND"}
        captured = float(cap["amount"]["value"])
        already = sum(float(r["amount"]["value"]) for r in REFUNDS.values() if r["capture_id"] == cid)
        amt = float(body.get("amount", {}).get("value", captured - already))
        if amt <= 0 or already + amt > captured + 1e-9:
            return 422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "REFUND_AMOUNT_EXCEEDED"}]}
        rid = _id("REF")
        refund = {"id": rid, "status": "COMPLETED", "capture_id": cid, "create_time": _now(),
                  "amount": {"value": f"{amt:.2f}", "currency_code": cap["amount"]["currency_code"]}}
        REFUNDS[rid] = refund
        cap["status"] = "REFUNDED" if abs(already + amt - captured) < 1e-9 else "PARTIALLY_REFUNDED"
        _event("PAYMENT.CAPTURE.REFUNDED", refund)
        return 201, refund
    if parts[:3] == ["v2", "payments", "refunds"] and method == "GET":
        r = REFUNDS.get(parts[3])
        return (200, r) if r else (404, {"name": "RESOURCE_NOT_FOUND"})
    # Invoicing v2
    if parts[:3] == ["v2", "invoicing", "invoices"]:
        if method == "POST" and len(parts) == 3:
            iid = _id("INV2-")
            inv = {"id": iid, "status": "DRAFT", **body}
            INVOICES[iid] = inv
            return 201, {"rel": "self", "href": f"/v2/invoicing/invoices/{iid}", "id": iid, "status": "DRAFT"}
        iid = parts[3]
        inv = INVOICES.get(iid)
        if not inv:
            return 404, {"name": "RESOURCE_NOT_FOUND"}
        if method == "POST" and parts[-1] == "send":
            inv["status"] = "SENT"
            return 200, {"href": f"https://mock.paypal.local/invoice/p/#{iid}"}
        if method == "GET":
            return 200, inv
    if path == "/v1/customer/disputes":
        return 200, {"items": []}
    if path == "/v1/reporting/balances":
        total = sum(float(c["amount"]["value"]) for c in CAPTURES.values())
        refunded = sum(float(r["amount"]["value"]) for r in REFUNDS.values())
        return 200, {"balances": [{"currency": "USD", "primary": True,
                                   "total_balance": {"currency_code": "USD", "value": f"{total - refunded:.2f}"}}]}
    return 404, {"name": "NOT_FOUND", "message": f"mock has no route for {method} {path}"}


_load()
MOCK_TRANSPORT = httpx.MockTransport(_handler)
