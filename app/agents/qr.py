"""Dynamic QR intelligence: work out what a scanned code actually contains.

Supported: ContextIQ signed codes (itemised, verifiable), UPI payment URIs, EMVCo merchant QR
(the format most bank/card QR codes use), PayPal.me links, and plain web links.
Only ContextIQ codes and PayPal links can be paid through PayPal here; for the others we show what
the code says and record it, but never pretend it is payable through PayPal.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def _emv_tlv(s: str) -> dict:
    out, i = {}, 0
    while i + 4 <= len(s):
        tag, ln = s[i:i + 2], int(s[i + 2:i + 4]) if s[i + 2:i + 4].isdigit() else -1
        if ln < 0 or i + 4 + ln > len(s):
            break
        out[tag] = s[i + 4:i + 4 + ln]
        i += 4 + ln
    return out


def interpret(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("ciq1."):
        return {"format": "ContextIQ signed bill", "payable_with_paypal": True, "itemised": True,
                "next": "verify_signature", "summary": "A signed, itemised bill from a ContextIQ merchant."}
    low = t.lower()
    if low.startswith("upi://pay"):
        q = {k: v[0] for k, v in parse_qs(urlparse(t).query).items()}
        return {"format": "UPI payment request", "payable_with_paypal": False, "itemised": False,
                "payee": q.get("pn") or q.get("pa"), "payee_address": q.get("pa"),
                "amount": float(q["am"]) if q.get("am") else None, "currency": q.get("cu", "INR"),
                "note": q.get("tn"),
                "summary": "A UPI code. It names the payee and maybe an amount, but no items. UPI payments go through "
                           "a UPI app, not PayPal."}
    if t.startswith("000201"):
        tlv = _emv_tlv(t)
        amount = float(tlv["54"]) if tlv.get("54", "").replace(".", "", 1).isdigit() else None
        return {"format": "EMVCo merchant QR", "payable_with_paypal": False, "itemised": False,
                "payee": tlv.get("59"), "city": tlv.get("60"), "amount": amount,
                "currency_code": tlv.get("53"), "dynamic": tlv.get("01") == "12",
                "summary": "A standard merchant QR (the kind banks and card networks use). It has the merchant name "
                           "and sometimes an amount, but not the items. It isn't payable through PayPal here."}
    if "paypal.me/" in low or "paypal.com/paypalme/" in low:
        parts = [p for p in urlparse(t if "://" in t else "https://" + t).path.split("/") if p]
        handle = parts[1] if parts and parts[0].lower() == "paypalme" and len(parts) > 1 else (parts[0] if parts else None)
        amount = None
        if len(parts) >= 2 and parts[-1].replace(".", "", 1).isdigit():
            amount = float(parts[-1])
        return {"format": "PayPal.me link", "payable_with_paypal": True, "itemised": False, "payee": handle,
                "amount": amount, "summary": "A PayPal.me link: payable with PayPal, but it carries no item details."}
    if low.startswith(("http://", "https://")):
        return {"format": "web link", "payable_with_paypal": False, "itemised": False, "url": t,
                "summary": "Just a web link. I won't open payment pages from unknown links automatically."}
    return {"format": "unknown", "payable_with_paypal": False, "itemised": False,
            "summary": "I couldn't recognise this code."}
