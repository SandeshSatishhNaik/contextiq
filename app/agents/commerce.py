"""Payment, checkout, refund, invoice and QR experts.

Experts prepare and propose. Money only moves through: gateway.check() → payments.*_safely().
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import briefcase as bc
from ..config import settings
from ..fmt import days as fdays
from ..fmt import money as fmoney
from ..intelligence.decision import Option, decide
from ..intelligence.reasoning import Fact, causal_chain, temporal, uncertainty
from ..models import (
    Agreement,
    Case,
    CaseEvent,
    LedgerEntry,
    Obligation,
    PolicySnapshot,
    PriceObservation,
    SecurityEvent,
    User,
)
from ..paypal import payments
from ..security import crypto, gateway, mandate
from . import budget as budget_agent
from . import context as ctx_agent
from . import policy as policy_agent


# ------------------------------------------------------------------ cart / checkout
def analyze_cart(db: Session, user_id: str, *, merchant: str, items: list[dict], currency: str,
                 policy_text: str = "", policy_url: str = "", page_url: str = "", channel: str = "online") -> dict:
    total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in items), 2)
    pol = policy_agent.extract(policy_text, policy_url, merchant) if policy_text else None
    prices = []
    for it in items:
        key = _product_key(merchant, it["name"])
        hist = db.scalars(select(PriceObservation).where(PriceObservation.product_key == key)
                          .order_by(PriceObservation.seen_at)).all()
        db.add(PriceObservation(user_id=user_id, product_key=key, title=it["name"], merchant=merchant,
                                price=float(it["unit_price"]), currency=currency, url=page_url))
        seen = [h.price for h in hist]
        info = {"item": it["name"], "price": float(it["unit_price"]), "observations": len(seen) + 1}
        if seen:
            low = min(seen)
            info |= {"lowest_seen": low, "highest_seen": max(seen),
                     "is_lowest_seen": float(it["unit_price"]) <= low,
                     "drop_from_last": round(seen[-1] - float(it["unit_price"]), 2)}
        prices.append(info)
    whatif = budget_agent.what_if(db, user_id, total, label=f"this cart ({fmoney(total, currency)})")
    ctx = ctx_agent.classify(db, user_id, merchant, " ".join(i["name"] for i in items), channel, total)
    risk = ctx_agent.assess_risk(db, user_id, merchant, total)
    return {
        "merchant": merchant, "total": total, "currency": currency, "channel": channel,
        "policy": None if not pol else {"summary": policy_agent.explain(pol["terms"]), "terms": pol["terms"],
                                        "unknown": pol["unknown"], "source": pol["source"], "cached": pol["cached"],
                                        "injection_flags": pol["injection_flags"]},
        "prices": prices, "budget": whatif, "context": ctx, "risk": risk,
    }


def _policy_short(t: dict) -> str:
    parts = []
    if t.get("return_window_days"):
        parts.append(f"{t['return_window_days']}-day returns from {t.get('starts_from', 'purchase')}")
    if t.get("replacement_window_days"):
        parts.append(f"{t['replacement_window_days']}-day replacement")
    if t.get("warranty_days"):
        parts.append(f"{round(t['warranty_days'] / 30)}-month warranty")
    if t.get("exclusions"):
        parts.append(f"{len(t['exclusions'])} exclusion(s)")
    return ", ".join(parts) or "no windows stated"


def _product_key(merchant: str, name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{merchant}-{name}".lower()).strip("-")


def start_checkout(db: Session, user_id: str, *, merchant: str, items: list[dict], currency: str,
                   policy_text: str = "", policy_url: str = "", channel: str = "online",
                   seller_id: str | None = None, payee_email: str | None = None, purpose: str | None = None,
                   category: str = "general") -> dict:
    """Records proof of intent, creates the briefcase and the PayPal order, returns the approval link."""
    total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in items), 2)
    ctx = ctx_agent.classify(db, user_id, merchant, " ".join(i["name"] for i in items), channel, total)
    case = bc.create_case(db, owner_id=user_id, title=", ".join(i["name"] for i in items)[:120], merchant=merchant,
                          amount=total, currency=currency, channel=channel, purpose=purpose or ctx["purpose"],
                          category=ctx["category"] if category == "general" else category,
                          counterparty_id=seller_id)
    terms = {}
    if policy_text:
        pol = policy_agent.extract(policy_text, policy_url, merchant)
        terms = pol["terms"]
        db.add(PolicySnapshot(case_id=case.id, merchant=merchant, url=policy_url, content_hash=pol["hash"],
                              text=policy_text[:20000], extracted=terms))
        bc.add_evidence(db, case, kind="policy_snapshot", source="merchant_page", provenance="claimed",
                        summary=f"{merchant} policy as shown at purchase: " + _policy_short(terms),
                        content={"terms": terms, "url": policy_url})
    ag = bc.record_agreement(db, case, items=items, amount=total, currency=currency, payee=merchant,
                             terms=terms, approved_by=user_id)
    m = mandate.issue(db, case, ag, payer=user_id)
    db.flush()
    agreement_ev = db.scalars(select(bc.Evidence).where(bc.Evidence.case_id == case.id,
                                                        bc.Evidence.kind == "agreement")).first()
    bc.add_evidence(db, case, kind="classification", source="context_model", provenance="inferred",
                    summary=f"Classified as {case.purpose} / {case.category} ({ctx['purpose_confidence']:.0%})",
                    content=ctx, cites=[agreement_ev.id] if agreement_ev else [], visible_to="buyer")
    # PayPal's order record carries the mandate hash, so the payment points back to what the buyer signed.
    order = payments.create_order_for_case(db, case, items, payee_email=payee_email, custom_id=f"ciqm:{m['hash']}")
    approval = gateway.issue_approval(db, user_id=user_id, case=case, action="capture")
    db.commit()
    return {"case_id": case.id, "order": order, "approval_token": approval.token, "amount": total,
            "currency": currency, "classification": ctx}


def complete_payment(db: Session, user_id: str, case_id: str, approval_token: str,
                     step_up_code: str | None = None, signals: dict | None = None) -> dict:
    case = db.get(Case, case_id)
    if not case:
        return {"ok": False, "error": "case not found"}
    # Read-only check first: a capture attempted before the buyer approves on PayPal must not
    # consume the one-time approval token.
    state = payments.sync_order_state(db, case)
    if state["order_status"] not in ("APPROVED", "COMPLETED"):
        return {"ok": False, "error": f"buyer has not approved the order on PayPal yet ({state['order_status']})"}
    ok, why = mandate.verify(db, case)
    if not ok:  # fail closed: no valid signed mandate, no capture
        db.add(SecurityEvent(user_id=user_id, kind="mandate_denied", severity="warning", detail={"case": case.id, "reason": why}))
        return {"ok": False, "gateway": "deny", "reasons": [why]}
    if step_up_code:
        gateway.pass_step_up(db, approval_token, step_up_code)
    risk = ctx_agent.assess_risk(db, user_id, case.merchant, case.amount, **(signals or {}))
    verdict = gateway.check(db, actor=user_id, action="capture", case=case, approval_token=approval_token, risk=risk)
    if not verdict.allowed:
        return {"ok": False, "gateway": verdict.decision, "reasons": verdict.reasons,
                "step_up_code_demo": verdict.step_up_code, "risk": risk}
    result = payments.capture_safely(db, case)
    if result["ok"]:
        _after_capture(db, case, user_id)
    return result | {"gateway": verdict.decision, "risk": risk, "case_id": case.id}


def _after_capture(db: Session, case: Case, user_id: str) -> None:
    if not db.scalar(select(LedgerEntry).where(LedgerEntry.case_id == case.id)):
        db.add(LedgerEntry(user_id=user_id, case_id=case.id, payee=case.merchant, description=case.title,
                           category=case.category, purpose=case.purpose, amount=case.amount, source="contextiq"))
    snap = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case.id))
    if snap and not db.scalar(select(Obligation).where(Obligation.case_id == case.id)):
        t = snap.extracted
        base = datetime.now(UTC) + (timedelta(days=5) if t.get("starts_from") == "delivery" else timedelta())
        for kind, key in (("return_window", "return_window_days"), ("replacement_window", "replacement_window_days"),
                          ("warranty", "warranty_days")):
            if t.get(key):
                db.add(Obligation(owner_id=user_id, case_id=case.id, kind=kind,
                                  title=f"{kind.replace('_', ' ').title()} — {case.title}",
                                  due_at=base + timedelta(days=int(t[key])), amount=0))
        if t.get("starts_from") == "delivery":
            db.add(Obligation(owner_id=user_id, case_id=case.id, kind="delivery", title=f"Delivery — {case.title}",
                              due_at=base, amount=0))


def record_delivery(db: Session, case_id: str, delivered_at: datetime | None = None, source: str = "merchant") -> dict:
    """Delivery confirmation moves deadlines that run 'from delivery'."""
    case = db.get(Case, case_id)
    delivered_at = delivered_at or datetime.now(UTC)
    bc.add_event(db, case, "delivered", source, {"at": delivered_at.isoformat()})
    snap = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case_id))
    for o in db.scalars(select(Obligation).where(Obligation.case_id == case_id)).all():
        if o.kind == "delivery":
            o.status = "done"
        elif snap and snap.extracted.get("starts_from") == "delivery":
            key = {"return_window": "return_window_days", "replacement_window": "replacement_window_days",
                   "warranty": "warranty_days"}.get(o.kind)
            if key and snap.extracted.get(key):
                o.due_at = delivered_at + timedelta(days=int(snap.extracted[key]))
    return {"ok": True}


# ---------------------------------------------------------------------- refund & remedies (swap, warranty, dispute)
def build_refund_options(windows: dict, defect: bool, evidence_conf: float, captured: bool, best: str | None,
                         prefers_refund: bool = False, prefers_swap: bool = False) -> list[Option]:
    """Options for the decision model. `permitted` comes from policy facts; the model only ranks."""
    def open_(k):
        return windows.get(k, {}).get("status") in ("open", "closing")

    closing = any(windows.get(k, {}).get("status") == "closing" for k in windows)
    return [
        Option("request_refund", {"benefit": 1.0 if not defect else 0.7, "risk": 0.1, "urgency": 1.0 if closing else 0.4,
                                  "reversibility": 0.5, "evidence": evidence_conf, "cost": 0.3,
                                  "user_preference": 1.0 if prefers_refund else 0.0},
               permitted=captured and open_("return_window"), explanation="Money back to your original payment method"),
        Option("request_replacement", {"benefit": 0.95 if defect else 0.6, "risk": 0.1, "urgency": 0.7 if closing else 0.4,
                                       "reversibility": 0.7, "evidence": evidence_conf, "cost": 0.2,
                                       "user_preference": 1.0 if prefers_swap else (0.0 if prefers_refund else 0.5)},
               permitted=captured and (defect or prefers_swap) and open_("replacement_window"), explanation="Free swap: get the same item replaced"),
        Option("warranty_claim", {"benefit": 0.5, "risk": 0.05, "urgency": 0.2, "reversibility": 0.9,
                                  "evidence": evidence_conf, "cost": 0.5, "user_preference": 0.2},
               permitted=captured and defect and open_("warranty"), explanation="Have it repaired under warranty"),
        Option("escalate_to_paypal_protection", {"benefit": 0.4, "risk": 0.2, "urgency": 0.3, "reversibility": 0.3,
                                                 "evidence": evidence_conf, "cost": 0.7, "user_preference": 0.1},
               permitted=captured and not best, explanation="Open a case with PayPal Purchase Protection"),
    ]


def refund_eligibility(db: Session, case: Case, issue: str = "", now: datetime | None = None) -> dict:
    """Deterministic: policy JSON + dates. The model never decides eligibility."""
    now = now or datetime.now(UTC)
    snap = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case.id))
    obs = {o.kind: o for o in db.scalars(select(Obligation).where(Obligation.case_id == case.id)).all()}
    delivered = db.scalar(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.type == "delivered"))
    facts = []
    if case.paypal_capture_id:
        facts.append(Fact("payment_captured", True, "verified"))
    if snap:
        facts.append(Fact("policy_terms", snap.extracted, "claimed"))
    if delivered:
        facts.append(Fact("delivery_date", delivered.payload.get("at"), "verified" if delivered.source != "user" else "claimed"))
    unc = uncertainty(["payment_captured", "policy_terms", "delivery_date"], facts)
    windows = {}
    for kind in ("return_window", "replacement_window", "warranty"):
        if kind in obs:
            windows[kind] = temporal(obs[kind].due_at, now) | {"due": _aware(obs[kind].due_at).date().isoformat()}
    defect = bool(re.search(r"stopped working|broken|defect|damaged|not working|faulty|dead", issue, re.I))
    prefers_swap = bool(re.search(r"\b(swap|replace|replacement|exchange|switch)\b", issue, re.I))
    prefers_refund = bool(re.search(r"\b(money back|refund|return for money|cash back)\b", issue, re.I))
    if not case.paypal_capture_id:
        best = None
        reason = "PayPal hasn't confirmed a payment for this order yet, so there's nothing to refund or swap."
    elif case.payment_state == "refunded":
        best, reason = None, "This order has already been fully refunded."
    else:
        if prefers_swap and windows.get("replacement_window", {}).get("status") in ("open", "closing"):
            order = ["replacement_window", "return_window", "warranty"]
        elif defect:
            order = ["replacement_window", "return_window", "warranty"]
        else:
            order = ["return_window", "replacement_window", "warranty"]
        best = next((k for k in order if windows.get(k, {}).get("status") in ("open", "closing")), None)
        label = {"return_window": "return it for a refund", "replacement_window": "swap it free for a replacement",
                 "warranty": "get it repaired under warranty"}
        if best:
            reason = (f"Good news — you can still {label[best]}: {fdays(windows[best]['days_left'])} left "
                      f"(until {windows[best]['due']}).")
        elif windows:
            reason = ("The store's return and replacement windows have closed. "
                      "PayPal Purchase Protection may still help.")
        else:
            reason = "The store's policy didn't say how long you have, so I can't confirm you're covered."
    options = build_refund_options(windows, defect, unc["confidence"], bool(case.paypal_capture_id), best,
                                   prefers_refund=prefers_refund, prefers_swap=prefers_swap)
    return {"options": options, "eligible": bool(best), "basis": best, "reason": reason, "windows": windows, "uncertainty": unc,
            "decision": decide(options), "defect_reported": defect, "prefers_swap": prefers_swap}


def merchant_refund(db: Session, seller_id: str, case_id: str, approval_token: str, amount: float | None = None,
                    reason: str = "") -> dict:
    case = db.get(Case, case_id)
    verdict = gateway.check(db, actor=seller_id, action="refund", case=case, approval_token=approval_token,
                            amount=amount if amount is not None else case.amount)
    if not verdict.allowed:
        return {"ok": False, "gateway": verdict.decision, "reasons": verdict.reasons,
                "step_up_code_demo": verdict.step_up_code}
    res = payments.refund_safely(db, case, amount=amount, reason=reason)
    if res.get("ok"):
        db.add(LedgerEntry(user_id=case.owner_id, case_id=case.id, payee=case.merchant, description="refund",
                           category=case.category, purpose=case.purpose,
                           amount=-(amount if amount is not None else case.amount), source="paypal_refund"))
        for o in db.scalars(select(Obligation).where(Obligation.case_id == case.id, Obligation.status == "open")).all():
            if o.kind in ("return_window", "replacement_window"):
                o.status = "done"
    return res


def draft_claim(db: Session, case: Case, issue: str) -> dict:
    elig = refund_eligibility(db, case, issue)
    ev = bc.add_evidence(db, case, kind="claim_draft", source="refund_expert", provenance="claimed",
                         summary=f"Buyer reports: {issue[:200]}", content={"issue": issue})
    choice = (elig["decision"]["choice"] or {}).get("name")
    bc.add_event(db, case, "claim_prepared", "ai", {"basis": elig["basis"], "recommended": choice, "evidence": ev.id})
    return {"eligibility": elig, "claim": {
        "to": case.merchant, "order": case.paypal_order_id, "capture": case.paypal_capture_id,
        "amount": case.amount, "currency": case.currency, "request": choice, "issue": issue,
        "policy_basis": elig["reason"]}}


def execute_resolution(db: Session, case: Case, action: str, issue: str = "", user_id: str = "") -> dict:
    """Executes buyer post-purchase remedies: replacement/swap, warranty claim, or PayPal dispute."""
    if action in ("request_replacement", "swap"):
        ev = bc.add_evidence(db, case, kind="replacement_claim", source="buyer", provenance="claimed",
                             summary=f"Replacement / Free Swap requested: {issue or 'Defective unit swap'}",
                             content={"action": "swap", "issue": issue})
        bc.add_event(db, case, "replacement_requested", "buyer", {"action": "swap", "evidence": ev.id})
        for o in db.scalars(select(Obligation).where(Obligation.case_id == case.id, Obligation.kind == "replacement_window")).all():
            o.status = "done"
        db.commit()
        return {"ok": True, "action": "swap", "message": f"Replacement request recorded for {case.merchant}. The merchant still has to confirm it; it is saved in your briefcase as your claim."}

    elif action in ("warranty_claim", "warranty"):
        ev = bc.add_evidence(db, case, kind="warranty_claim", source="buyer", provenance="claimed",
                             summary=f"Warranty repair claim submitted: {issue or 'Hardware defect under warranty'}",
                             content={"action": "warranty", "issue": issue})
        bc.add_event(db, case, "warranty_claimed", "buyer", {"action": "warranty", "evidence": ev.id})
        for o in db.scalars(select(Obligation).where(Obligation.case_id == case.id, Obligation.kind == "warranty")).all():
            o.status = "in_progress"
        db.commit()
        return {"ok": True, "action": "warranty", "message": f"Warranty claim recorded for {case.merchant}. The merchant still has to confirm it; it is saved in your briefcase as your claim."}

    elif action in ("escalate_to_paypal_protection", "paypal_dispute"):
        # Buyers open PayPal cases on PayPal itself (the Disputes API is seller-side), so this prepares the
        # case file and points there. It is the buyer's claim until PayPal reports a dispute back.
        ev = bc.add_evidence(db, case, kind="paypal_dispute_prepared", source="buyer", provenance="claimed",
                             summary=f"Case file prepared for PayPal Purchase Protection (order {case.paypal_order_id or case.id})",
                             content={"action": "paypal_dispute", "order_id": case.paypal_order_id, "capture_id": case.paypal_capture_id})
        bc.add_event(db, case, "dispute_prepared", "buyer", {"action": "paypal_protection", "order_id": case.paypal_order_id})
        db.commit()
        return {"ok": True, "action": "paypal_protection",
                "message": f"Case file prepared. Open the case on PayPal (Resolution Center) for order {case.paypal_order_id or case.id}; "
                           "ContextIQ picks it up from PayPal once it is filed.",
                "open_url": "https://www.paypal.com/resolutioncenter"}

    return {"ok": False, "error": f"Unknown resolution action: {action}"}


# --------------------------------------------------------------------- invoice
def check_invoice(db: Session, user_id: str, *, supplier: str, po: dict, invoice: dict, text: str = "",
                  payee_changed_recently: bool = False) -> dict:
    """Dispute prevention: compare invoice to the agreed purchase order before anyone pays."""
    issues = []
    po_total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in po["items"]), 2)
    inv_total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in invoice["items"]), 2)
    po_items = {i["name"].lower(): i for i in po["items"]}
    for it in invoice["items"]:
        ref = po_items.get(it["name"].lower())
        if not ref:
            issues.append(f"'{it['name']}' is on the invoice but not on the purchase order")
            continue
        if int(it.get("quantity", 1)) != int(ref.get("quantity", 1)):
            issues.append(f"'{it['name']}': quantity {it.get('quantity')} invoiced vs {ref.get('quantity')} ordered")
        if abs(float(it["unit_price"]) - float(ref["unit_price"])) > 0.005:
            issues.append(f"'{it['name']}': unit price {float(it['unit_price']):.2f} vs agreed {float(ref['unit_price']):.2f}")
    for name in po_items:
        if name not in {i["name"].lower() for i in invoice["items"]}:
            issues.append(f"'{po_items[name]['name']}' was ordered but is missing from the invoice")
    if invoice.get("payee") and po.get("payee") and invoice["payee"] != po["payee"]:
        issues.append(f"payee changed: invoice asks for {invoice['payee']}, agreement says {po['payee']}")
        payee_changed_recently = True
    ratio = inv_total / po_total if po_total else 1.0
    risk = ctx_agent.assess_risk(db, user_id, supplier, inv_total, invoice_po_ratio=ratio, text=text,
                                 payee_changed_recently=payee_changed_recently)
    if issues:
        rec = "Don't pay yet — ask the supplier for a corrected invoice, or agree the changes in writing first."
    elif risk["decision"] != "allow":
        rec = "The amounts match, but something about this request is unusual. Confirm with the supplier using a contact you already had."
    else:
        rec = "The invoice matches what you ordered. You can go ahead when you're ready."
    return {"po_total": po_total, "invoice_total": inv_total, "difference": round(inv_total - po_total, 2),
            "ratio": round(ratio, 3), "issues": issues, "risk": risk, "recommendation": rec,
            "status": "mismatch" if issues else ("verify" if risk["decision"] != "allow" else "match")}


# ---------------------------------------------------------- QR + buyer/seller link
def merchant_create_qr(db: Session, seller_id: str, *, items: list[dict], currency: str,
                       policy_text: str = "") -> dict:
    seller = db.get(User, seller_id)
    merchant = seller.business_name or seller.name
    total = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in items), 2)
    token = crypto.sign_message({"typ": "ciq.pay", "merchant_id": seller_id, "merchant": merchant,
                                 "items": items, "amount": total, "currency": currency,
                                 "policy": policy_text[:2000]})
    return {"qr_token": token, "amount": total, "currency": currency, "merchant": merchant,
            "expires_in_s": settings.qr_ttl_seconds, "public_key": crypto.public_key_b64()}


def buyer_scan_qr(db: Session, buyer_id: str, token: str) -> dict:
    try:
        body = crypto.verify_message(db, token)
    except crypto.TokenError as exc:
        from ..security import sentra

        sentra.ingest(db, kind="qr_rejected", user_id=buyer_id, severity="warning", detail={"reason": str(exc)})
        return {"ok": False, "error": str(exc)}
    out = start_checkout(db, buyer_id, merchant=body["merchant"], items=body["items"], currency=body["currency"],
                         policy_text=body.get("policy", ""), channel="in_person", seller_id=body["merchant_id"])
    case = db.get(Case, out["case_id"])
    if case:
        bc.add_evidence(db, case, kind="signed_qr", source="contextiq_qr", provenance="verified",
                        summary=f"Itemised bill signed by {body['merchant']} (Ed25519, nonce {body['nonce'][:6]}…)",
                        content={"items": body["items"], "amount": body["amount"], "iat": body["iat"]})
        db.commit()
    return {"ok": True, "verified_merchant": body["merchant"], "items": body["items"]} | out


def payment_investigation(db: Session, case: Case, asker_role: str = "buyer",
                          supplier_claim: str = "payment not received") -> dict:
    """'Why does my supplier say payment wasn't received?' — check PayPal first, then explain."""
    if case.paypal_order_id:
        try:
            payments.sync_order_state(db, case)
        except Exception as exc:  # noqa: BLE001
            bc.add_event(db, case, "sync_failed", "system", {"error": str(exc)})
    events = [{"type": e.type, "source": e.source} for e in
              db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.occurred_at)).all()]
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    cause = causal_chain({"paypal_capture_id": case.paypal_capture_id}, events,
                         {"payee": ag.payee} if ag else None)
    claim_ev = bc.add_evidence(db, case, kind="counterparty_claim", source="supplier", provenance="claimed",
                               summary=f"Supplier says: {supplier_claim}", content={"claim": supplier_claim})
    facts = [Fact("paypal_state", case.payment_state, "verified")]
    if ag:
        facts.append(Fact("agreement", ag.signed_hash, "verified"))
    facts.append(Fact("supplier_claim", supplier_claim, "claimed"))
    unc = uncertainty(["paypal_state", "agreement", "supplier_claim", "payee_bank_statement"], facts)
    next_step = {
        "paid": "Share the PayPal capture ID with the supplier and ask them to check their PayPal balance "
                "(not their bank). Do not pay again.",
        "refunded": "Tell the supplier a refund was issued; agree whether a new payment is due.",
        "pending": "Wait for PayPal to release the hold; don't pay again. I'll watch for the update.",
        "approved_not_captured": "The payment was approved but never completed — complete it (with your approval).",
        "not_paid": "No payment reached PayPal. Retry the payment with your approval.",
        "not_started": "No payment exists yet.",
        "paid_to_different_account": "Confirm the supplier's correct PayPal account before anything else.",
    }.get(cause["verdict"], "Ask the supplier for their transaction reference.")
    bc.add_evidence(db, case, kind="investigation", source="resolution_expert", provenance="inferred",
                    summary=f"Finding: {cause['verdict']}. {cause['chain'][0]}",
                    content=cause, cites=[claim_ev.id])
    return {"verdict": cause["verdict"], "explanation": cause["chain"], "next_step": next_step,
            "uncertainty": unc, "capture_id": case.paypal_capture_id, "payment_state": case.payment_state}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
