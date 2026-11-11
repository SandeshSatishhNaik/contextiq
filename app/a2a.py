"""ContextIQ agent-to-agent (A2A-style) protocol between a buyer's agent and a seller's agent.

Identity:   each agent has an Ed25519 key pair; its *agent card* (id, role, capabilities, public key) is
            signed by the ContextIQ key registry. Keys can be rotated and revoked.
Messages:   envelopes {v, id, session, from, to, type, ts, nonce, body} signed by the sender.
            A receiver accepts a message only if: the card is registry-signed and not revoked, the
            signature matches, it is addressed to the receiver, it is fresh (≤120 s) and the nonce is new.
Session:    HELLO → ACCEPT → CONTEXT (both ways, permission-filtered) → COMPARE → PAYMENT_UPDATE → CLOSE.
Permissions: each side shares only what its role allows. A buyer's budget, other purchases or investments
            are never in any message. Sync state is tracked separately from the PayPal payment state, so a
            failed sync can never turn a completed payment into a failed one.
Transport:  in-process for the demo (both agents run on this server); `POST /a2a/inbox` accepts the same
            envelopes over HTTP, so a separate ContextIQ instance can be the other side.
"""
from __future__ import annotations

import base64
import json
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import briefcase as bc
from .fmt import money
from .models import (
    A2AMessage,
    A2ASession,
    AgentKey,
    Agreement,
    Case,
    Invoice,
    Participant,
    UsedNonce,
    User,
)
from .paypal import payments
from .security import crypto

FRESH_SECONDS = 120
CAPABILITIES = {"buyer": ["share_order", "confirm_delivery", "payment_update", "compare"],
                "seller": ["share_invoice", "share_delivery", "share_policy", "compare"]}
# what each role may put in a CONTEXT message — everything else is stripped before signing
SHAREABLE = {"buyer": {"order_items", "agreed_amount", "currency", "agreed_payee", "agreement_hash", "payment_state",
                       "paypal_capture_id", "delivery_received"},
             "seller": {"invoice_items", "invoice_amount", "currency", "payee", "delivery_promise", "policy_summary"}}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _canon(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode()


# ------------------------------------------------------------- identity / registry
def ensure_agent(db: Session, party_id: str, role: str) -> AgentKey:
    k = db.scalar(select(AgentKey).where(AgentKey.party_id == party_id, AgentKey.role == role,
                                         AgentKey.revoked.is_(False)))
    if k:
        return k
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    k = AgentKey(key_id=uuid.uuid4().hex[:12], agent_id=f"agent:{role}:{party_id}", party_id=party_id, role=role,
                 private_pem=priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()).decode(),
                 public_b64=_b64(pub))
    db.add(k)
    db.flush()
    return k


def agent_card(db: Session, k: AgentKey) -> dict:
    user = db.get(User, k.party_id)
    card = {"agent_id": k.agent_id, "key_id": k.key_id, "role": k.role,
            "name": (user.business_name or user.name) if user else k.party_id,
            "capabilities": CAPABILITIES[k.role], "public_key": k.public_b64, "protocol": "contextiq-a2a/1"}
    sig = crypto._PRIVATE.sign(_canon(card))  # registry signature
    return card | {"registry_signature": _b64(sig)}


def rotate_key(db: Session, party_id: str, role: str) -> AgentKey:
    for k in db.scalars(select(AgentKey).where(AgentKey.party_id == party_id, AgentKey.role == role)).all():
        k.revoked = True
    db.flush()
    return ensure_agent(db, party_id, role)


def _verify_card(db: Session, card: dict) -> AgentKey:
    body = {k: v for k, v in card.items() if k != "registry_signature"}
    try:
        crypto.PUBLIC.verify(_unb64(card["registry_signature"]), _canon(body))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("agent card is not signed by the ContextIQ registry") from exc
    k = db.get(AgentKey, card["key_id"])
    if not k or k.public_b64 != card["public_key"]:
        raise ValueError("unknown agent key")
    if k.revoked:
        raise ValueError("agent key has been revoked")
    return k


# ---------------------------------------------------------------------- messages
def make_envelope(db: Session, sender: AgentKey, receiver_agent_id: str, session_id: str, type_: str,
                  body: dict) -> dict:
    if type_ == "CONTEXT":
        body = {k: v for k, v in body.items() if k in SHAREABLE[sender.role]}  # permission filter before signing
    env = {"v": 1, "id": uuid.uuid4().hex, "session": session_id, "from": sender.agent_id, "to": receiver_agent_id,
           "type": type_, "ts": int(time.time()), "nonce": uuid.uuid4().hex, "body": body,
           "card": agent_card(db, sender)}
    priv = serialization.load_pem_private_key(sender.private_pem.encode(), password=None)
    env["sig"] = _b64(priv.sign(_canon({k: v for k, v in env.items() if k != "card"})))
    return env


def receive(db: Session, receiver: AgentKey, env: dict) -> tuple[bool, str]:
    """Verify an incoming envelope. Every attempt is logged; rejected messages are kept as security evidence."""
    reason = ""
    try:
        sk = _verify_card(db, env["card"])
        if sk.agent_id != env["from"]:
            raise ValueError("sender does not match its card")
        if env["to"] != receiver.agent_id:
            raise ValueError("message is addressed to another agent")
        pub = Ed25519PublicKey.from_public_bytes(_unb64(sk.public_b64))
        pub.verify(_unb64(env["sig"]), _canon({k: v for k, v in env.items() if k not in ("card", "sig")}))
        if abs(time.time() - env["ts"]) > FRESH_SECONDS:
            raise ValueError("message is stale")
        if db.get(UsedNonce, f"a2a:{env['nonce']}"):
            raise ValueError("replayed message")
        if env["type"] == "CONTEXT" and set(env["body"]) - SHAREABLE[sk.role]:
            raise ValueError("message carries fields this agent may not share")
        db.add(UsedNonce(value=f"a2a:{env['nonce']}"))
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok, reason = False, str(exc) or type(exc).__name__
        from .security import sentra

        sentra.ingest(db, kind="a2a_rejected", severity="warning", detail={"reason": reason, "type": env.get("type")})
    if not db.get(A2AMessage, env.get("id", "")):
        db.add(A2AMessage(id=env.get("id", uuid.uuid4().hex), session_id=env.get("session", ""), sender=env.get("from", ""),
                          receiver=receiver.agent_id, type=env.get("type", ""), envelope=env, verified=ok,
                          rejection=reason or None))
    db.flush()
    return ok, reason


# ------------------------------------------------------------------ the handshake
def _buyer_context(db: Session, case: Case) -> dict:
    ag = db.scalar(select(Agreement).where(Agreement.case_id == case.id))
    from .models import CaseEvent

    delivered = db.scalar(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.type == "delivered"))
    return {"order_items": ag.items if ag else [], "agreed_amount": ag.amount if ag else case.amount,
            "currency": case.currency, "agreed_payee": ag.payee if ag else case.merchant,
            "agreement_hash": ag.signed_hash if ag else None, "payment_state": case.payment_state,
            "paypal_capture_id": case.paypal_capture_id, "delivery_received": bool(delivered),
            # these exist in the buyer's memory but are NOT shareable — the filter removes them:
            "monthly_budget_left": "private", "other_purchases": "private"}


def _seller_context(db: Session, case: Case, seller_id: str) -> dict:
    inv = db.scalar(select(Invoice).where(Invoice.case_id == case.id))
    items = inv.items if inv else (db.scalar(select(Agreement).where(Agreement.case_id == case.id)).items)
    amount = round(sum(float(i["unit_price"]) * int(i.get("quantity", 1)) for i in items), 2)
    seller = db.get(User, seller_id)
    return {"invoice_items": items, "invoice_amount": amount, "currency": case.currency,
            "payee": seller.business_name or seller.name, "delivery_promise": "within 5 days",
            "policy_summary": "see shared policy"}


def compare_context(buyer: dict, seller: dict) -> dict:
    issues = []
    if abs(float(buyer.get("agreed_amount", 0)) - float(seller.get("invoice_amount", 0))) > 0.005:
        issues.append(f"amount: buyer agreed {money(buyer['agreed_amount'], buyer.get('currency', 'USD'))}, "
                      f"seller invoiced {money(seller['invoice_amount'], seller.get('currency', 'USD'))}")
    if buyer.get("agreed_payee") and seller.get("payee") and buyer["agreed_payee"] != seller["payee"]:
        issues.append(f"payee: buyer agreed to pay {buyer['agreed_payee']}, seller identifies as {seller['payee']}")
    bi = {i["name"].lower(): i for i in buyer.get("order_items", [])}
    for it in seller.get("invoice_items", []):
        ref = bi.get(it["name"].lower())
        if not ref:
            issues.append(f"'{it['name']}' is invoiced but wasn't in the order")
        elif int(ref.get("quantity", 1)) != int(it.get("quantity", 1)):
            issues.append(f"'{it['name']}': ordered {ref.get('quantity', 1)}, invoiced {it.get('quantity', 1)}")
    return {"match": not issues, "issues": issues}


def run_session(db: Session, case_id: str, buyer_id: str, tamper: str | None = None) -> dict:
    """Full handshake between the buyer's and the seller's agents for one purchase."""
    case = db.get(Case, case_id)
    seller_part = db.scalar(select(Participant).where(Participant.case_id == case_id, Participant.role == "seller"))
    if not case or not seller_part:
        return {"ok": False, "error": "this purchase has no connected seller"}
    if case.owner_id != buyer_id:
        return {"ok": False, "error": "only the buyer can open this connection"}
    bk, sk = ensure_agent(db, buyer_id, "buyer"), ensure_agent(db, seller_part.party_id, "seller")
    sess = A2ASession(case_id=case_id, buyer_agent=bk.agent_id, seller_agent=sk.agent_id)
    db.add(sess)
    db.flush()
    transcript = []

    def send(frm: AgentKey, to: AgentKey, type_: str, body: dict, mutate=None):
        env = make_envelope(db, frm, to.agent_id, sess.id, type_, body)
        if mutate:
            mutate(env)
        ok, why = receive(db, to, env)
        transcript.append({"from": frm.role, "to": to.role, "type": type_, "verified": ok, "rejected_because": why or None,
                           "fields": sorted(env["body"].keys())})
        return ok, env

    ok, _ = send(bk, sk, "HELLO", {"intent": "reconcile purchase", "case_ref": case.id[:8]})
    if not ok:
        sess.state = "rejected"
        return {"ok": False, "session": sess.id, "transcript": transcript}
    send(sk, bk, "ACCEPT", {"scope": SHAREABLE["seller"] and "order, invoice, delivery, payment status"})
    sess.state = "accepted"
    mutate = None
    if tamper == "change_amount":
        def mutate(env):
            env["body"]["agreed_amount"] = 1.0  # altered after signing → signature check must fail
    ok_b, env_b = send(bk, sk, "CONTEXT", _buyer_context(db, case), mutate)
    ok_s, env_s = send(sk, bk, "CONTEXT", _seller_context(db, case, seller_part.party_id))
    if not (ok_b and ok_s):
        sess.state = "rejected"
        return {"ok": False, "session": sess.id, "transcript": transcript, "state": sess.state}
    sess.state = "context_exchanged"
    cmp_ = compare_context(env_b["body"], env_s["body"])
    send(bk, sk, "COMPARE", {"match": cmp_["match"], "issues": cmp_["issues"]})
    sess.state = "compared"
    sess.findings = cmp_
    bc.add_evidence(db, case, kind="a2a_comparison", source="contextiq_a2a",
                    provenance="verified" if cmp_["match"] else "claimed",
                    summary=("Buyer's and seller's agents compared signed records: everything matches."
                             if cmp_["match"] else "Agents found differences: " + "; ".join(cmp_["issues"])),
                    content=cmp_)
    bc.add_event(db, case, "a2a_compared", "contextiq_a2a", {"session": sess.id, "match": cmp_["match"]})
    return {"ok": True, "session": sess.id, "state": sess.state, "comparison": cmp_, "transcript": transcript,
            "shared_by_buyer": sorted(env_b["body"].keys()), "shared_by_seller": sorted(env_s["body"].keys())}


def sync_payment(db: Session, session_id: str, simulate_failure: bool = False) -> dict:
    """Tell the seller's agent about the payment. Sync failure never changes the payment state."""
    sess = db.get(A2ASession, session_id)
    case = db.get(Case, sess.case_id)
    bk = db.scalar(select(AgentKey).where(AgentKey.agent_id == sess.buyer_agent, AgentKey.revoked.is_(False)))
    sk = db.scalar(select(AgentKey).where(AgentKey.agent_id == sess.seller_agent, AgentKey.revoked.is_(False)))
    if case.paypal_order_id:
        try:
            payments.sync_order_state(db, case)  # authoritative state first
        except Exception:  # noqa: BLE001
            pass
    if simulate_failure or not (bk and sk):
        sess.sync_state = "sync_failed_will_retry"
        bc.add_event(db, case, "a2a_sync_failed", "contextiq_a2a", {"session": session_id})
        return {"ok": False, "sync_state": sess.sync_state, "payment_state": case.payment_state}
    env = make_envelope(db, bk, sk.agent_id, session_id, "PAYMENT_UPDATE",
                        {"payment_state": case.payment_state, "paypal_capture_id": case.paypal_capture_id})
    ok, why = receive(db, sk, env)
    sess.sync_state = "synced" if ok else "sync_failed_will_retry"
    if ok:
        sess.state = "synced"
        bc.add_event(db, case, "a2a_synced", "contextiq_a2a", {"session": session_id, "payment_state": case.payment_state})
    return {"ok": ok, "sync_state": sess.sync_state, "payment_state": case.payment_state, "reason": why or None}
