"""Run against the REAL PayPal sandbox with your .env credentials.

    python scripts/sandbox_check.py

Steps: OAuth → create order → (you approve as the sandbox buyer) → capture →
repeat capture with the same PayPal-Request-Id (must NOT charge twice) → partial refund →
read refund → list disputes → merchant balance. Prints PASS / FAIL per step.
Paste the output back if anything fails.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PAYPAL_ENV", "sandbox")

from app.config import settings  # noqa: E402
from app.paypal.adapter import PayPalClient, PayPalError, approve_link, capture_from_order  # noqa: E402

results: list[tuple[str, bool, str]] = []


def step(name: str, fn):
    try:
        detail = fn()
        results.append((name, True, str(detail)[:160]))
        print(f"PASS  {name}  {str(detail)[:160]}")
        return detail
    except PayPalError as e:
        results.append((name, False, f"{e.status} {e.body}"))
        print(f"FAIL  {name}  {e.status} {str(e.body)[:400]}")
    except Exception as e:  # noqa: BLE001
        results.append((name, False, repr(e)))
        print(f"FAIL  {name}  {e!r}")
    return None


def main() -> int:
    if settings.paypal_env != "sandbox":
        print("Set PAYPAL_ENV=sandbox in .env first.")
        return 2
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        print("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET missing in .env")
        return 2
    c = PayPalClient()
    run = uuid.uuid4().hex[:8]
    step("oauth token", lambda: c._access_token()[:12] + "…")
    order = step("create order", lambda: c.create_order(
        amount=12.00, currency=settings.currency, items=[{"name": "ContextIQ sandbox test", "unit_price": 12.00}],
        reference_id=f"ciq-{run}", description="ContextIQ sandbox check", request_id=f"order-{run}",
        return_url="https://example.com/return", cancel_url="https://example.com/cancel"))
    if not order:
        return 1
    print("\nOpen this link, log in with your SANDBOX PERSONAL (buyer) account and approve:\n ", approve_link(order))
    input("\nPress Enter after approving… ")
    step("order approved", lambda: (lambda o: o["status"] if o["status"] == "APPROVED" else
                                    (_ for _ in ()).throw(RuntimeError(f"status {o['status']}")))(c.get_order(order["id"])))
    first = step("capture", lambda: c.capture_order(order["id"], request_id=f"capture-{run}"))
    cap = capture_from_order(first) if first else None

    def idem():
        again = c.capture_order(order["id"], request_id=f"capture-{run}")
        cap2 = capture_from_order(again)
        if cap2 and cap and cap2["id"] == cap["id"]:
            return f"same capture {cap['id']} — no second charge"
        raise RuntimeError(f"unexpected second capture: {cap2}")
    step("idempotent retry (same request id)", idem)
    if cap:
        ref = step("partial refund 2.00", lambda: c.refund_capture(cap["id"], request_id=f"refund-{run}", amount=2.00,
                                                                   currency=settings.currency, note="ContextIQ test"))
        if ref:
            step("read refund", lambda: c.get_refund(ref["id"])["status"])
    step("list disputes", lambda: f"{len(c.list_disputes().get('items', []))} dispute(s)")
    step("merchant balances", lambda: c.merchant_balances().get("balances", [])[:1])
    ok = sum(r[1] for r in results)
    print(f"\n{ok}/{len(results)} steps passed.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
