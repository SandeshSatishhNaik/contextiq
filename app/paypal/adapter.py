"""PayPal REST adapter — the only code allowed to change payment state.

Calls PayPal's REST API directly over httpx:
  OAuth 2.0 client credentials   POST /v1/oauth2/token
  Orders v2                       POST /v2/checkout/orders, GET /v2/checkout/orders/{id},
                                  POST /v2/checkout/orders/{id}/capture
  Payments v2                     POST /v2/payments/captures/{id}/refund, GET /v2/payments/refunds/{id}
  Invoicing v2                    POST /v2/invoicing/invoices, POST .../{id}/send, GET .../{id}
  Disputes v1                     GET /v1/customer/disputes
  Webhook verification            POST /v1/notifications/verify-webhook-signature

Every write carries a `PayPal-Request-Id` idempotency key so a retry with the same key
is treated by PayPal as the same request (no duplicate capture or refund).

With PAYPAL_ENV=mock the same code runs against an in-process transport that returns
PayPal-shaped responses (see mock.py), so everything is testable offline.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import settings


class PayPalError(Exception):
    def __init__(self, status: int, body: Any):
        super().__init__(f"PayPal error {status}: {body}")
        self.status = status
        self.body = body


class PayPalClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        if transport is None and settings.paypal_env == "mock":
            from .mock import MOCK_TRANSPORT

            transport = MOCK_TRANSPORT
        self.base_url = settings.paypal_base_url
        self._http = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout)
        self._token: str | None = None
        self._token_exp = 0.0

    # ---------------------------------------------------------------- auth
    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = self._http.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(settings.paypal_client_id or "mock-id", settings.paypal_client_secret or "mock-secret"),
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            raise PayPalError(r.status_code, r.text)
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _request(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
                 request_id: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json",
                   "Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        r = self._http.request(method, path, json=json, params=params, headers=headers)
        if r.status_code >= 400:
            try:
                raise PayPalError(r.status_code, r.json())
            except ValueError:
                raise PayPalError(r.status_code, r.text)
        return r.json() if r.content else {}

    # -------------------------------------------------------------- orders
    def create_order(self, *, amount: float, currency: str, items: list[dict], reference_id: str,
                     description: str, request_id: str, return_url: str, cancel_url: str,
                     payee_email: str | None = None, payer_email: str | None = None) -> dict:
        item_total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in items), 2)
        unit: dict[str, Any] = {
            "reference_id": reference_id,
            "description": description[:127],
            "amount": {
                "currency_code": currency,
                "value": f"{amount:.2f}",
                "breakdown": {"item_total": {"currency_code": currency, "value": f"{item_total:.2f}"}},
            },
            "items": [
                {"name": i["name"][:127], "quantity": str(int(i.get("quantity", 1))),
                 "unit_amount": {"currency_code": currency, "value": f"{float(i['unit_price']):.2f}"}}
                for i in items
            ],
        }
        if payee_email:
            unit["payee"] = {"email_address": payee_email}
        body: dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [unit],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url, "cancel_url": cancel_url, "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING"}}},
        }
        if payer_email:
            body["payer"] = {"email_address": payer_email}
        return self._request("POST", "/v2/checkout/orders", json=body, request_id=request_id)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str, request_id: str) -> dict:
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id)

    def add_tracking(self, order_id: str, capture_id: str, tracking_number: str, carrier: str,
                     request_id: str) -> dict:
        """Orders v2 Add Tracking: attaches a shipment to the capture (used by PayPal for seller protection)."""
        return self._request("POST", f"/v2/checkout/orders/{order_id}/track",
                             json={"capture_id": capture_id, "tracking_number": tracking_number,
                                   "carrier": carrier, "notify_payer": False}, request_id=request_id)

    # ------------------------------------------------------------- refunds
    def refund_capture(self, capture_id: str, *, request_id: str, amount: float | None = None,
                       currency: str | None = None, note: str = "") -> dict:
        body: dict[str, Any] = {}
        if amount is not None:
            body["amount"] = {"value": f"{amount:.2f}", "currency_code": currency or settings.currency}
        if note:
            body["note_to_payer"] = note[:255]
        return self._request("POST", f"/v2/payments/captures/{capture_id}/refund", json=body, request_id=request_id)

    def get_refund(self, refund_id: str) -> dict:
        return self._request("GET", f"/v2/payments/refunds/{refund_id}")

    # ------------------------------------------------------------ invoicing
    def create_invoice(self, *, invoicer_email: str, recipient_email: str, items: list[dict], currency: str,
                       invoice_number: str, note: str, request_id: str) -> dict:
        body = {
            "detail": {"currency_code": currency, "invoice_number": invoice_number, "note": note[:4000]},
            "invoicer": {"email_address": invoicer_email},
            "primary_recipients": [{"billing_info": {"email_address": recipient_email}}],
            "items": [{"name": i["name"], "quantity": str(int(i.get("quantity", 1))),
                       "unit_amount": {"currency_code": currency, "value": f"{float(i['unit_price']):.2f}"}}
                      for i in items],
        }
        return self._request("POST", "/v2/invoicing/invoices", json=body, request_id=request_id)

    def send_invoice(self, invoice_id: str, request_id: str) -> dict:
        return self._request("POST", f"/v2/invoicing/invoices/{invoice_id}/send",
                             json={"send_to_invoicer": True}, request_id=request_id)

    def get_invoice(self, invoice_id: str) -> dict:
        return self._request("GET", f"/v2/invoicing/invoices/{invoice_id}")

    # ------------------------------------------------------------ disputes
    def list_disputes(self) -> dict:
        return self._request("GET", "/v1/customer/disputes")

    # ------------------------------------------------------------- balances
    def merchant_balances(self) -> dict:
        """Balances of the app's own merchant account only."""
        return self._request("GET", "/v1/reporting/balances")

    # ------------------------------------------------------------ webhooks
    def verify_webhook(self, headers: dict[str, str], event: dict) -> bool:
        if settings.paypal_env == "mock":
            return headers.get("paypal-transmission-sig") == "mock-signature"
        h = {k.lower(): v for k, v in headers.items()}
        body = {
            "auth_algo": h.get("paypal-auth-algo"),
            "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": event,
        }
        res = self._request("POST", "/v1/notifications/verify-webhook-signature", json=body)
        return res.get("verification_status") == "SUCCESS"


def approve_link(order: dict) -> str | None:
    for link in order.get("links", []):
        if link.get("rel") in ("payer-action", "approve"):
            return link.get("href")
    return None


def capture_from_order(order: dict) -> dict | None:
    for unit in order.get("purchase_units", []):
        caps = unit.get("payments", {}).get("captures", [])
        if caps:
            return caps[0]
    return None


_client: PayPalClient | None = None


def get_client() -> PayPalClient:
    global _client
    if _client is None or (settings.paypal_env != "mock" and _client._http._transport is not None):
        _client = PayPalClient()
    return _client
