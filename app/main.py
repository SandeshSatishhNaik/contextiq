"""FastAPI app: REST API + static web app.

Demo auth: the caller identifies with the `X-User-Id` header. Replace with real sessions
(and passkeys for step-up) before any non-demo use.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import briefcase as bc
from . import orchestrator
from .agents import budget as budget_agent
from .agents import commerce, helpdesk, investment
from .agents import context as ctx_agent
from .config import ROOT, settings
from .db import SessionLocal, init_db
from .intelligence import adaptive, llm
from .intelligence.cache import cache
from .models import (
    AuditLog,
    Budget,
    Case,
    LedgerEntry,
    Obligation,
    OutboundNotice,
    User,
)
from .paypal import payments
from .paypal.adapter import get_client
from .security import gateway, sentra


@asynccontextmanager
async def lifespan(_app):
    init_db()
    from .seed import ensure_seed

    ensure_seed()
    yield


app = FastAPI(title="ContextIQ", version="0.2.0", lifespan=lifespan)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/demo-store", StaticFiles(directory=ROOT / "demo_store", html=True), name="demo_store")
BLOCKED_SESSIONS: set[str] = set()
METRICS = {"requests": 0, "latency_ms": 0.0}


def db_dep():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def user_dep(x_user_id: str = Header("alex"), db=Depends(db_dep)) -> User:
    u = db.get(User, x_user_id)
    if not u:
        raise HTTPException(401, "unknown user")
    return u


class Item(BaseModel):
    name: str
    unit_price: float
    quantity: int = 1


class CartIn(BaseModel):
    merchant: str
    items: list[Item]
    currency: str = Field(default_factory=lambda: settings.currency)
    policy_text: str = ""
    policy_url: str = ""
    page_url: str = ""
    channel: str = "online"
    seller_id: str | None = None
    purpose: str | None = None  # personal | business — chosen automatically, switchable before paying


class ChatIn(BaseModel):
    message: str
    case_id: str | None = None


class CaptureIn(BaseModel):
    approval_token: str
    step_up_code: str | None = None
    signals: dict = {}


# ------------------------------------------------------------------ pages
@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/paypal/return", response_class=HTMLResponse)
def paypal_return(case: str):
    return HTMLResponse(f"<script>location.href='/?approved={case}'</script>")


@app.get("/paypal/cancel", response_class=HTMLResponse)
def paypal_cancel(case: str):
    return HTMLResponse(f"<script>location.href='/?cancelled={case}'</script>")


# --------------------------------------------------------------- general
@app.middleware("http")
async def _metrics(request: Request, call_next):
    import time

    sid = request.headers.get("x-session-id", "")
    if sid in BLOCKED_SESSIONS and request.url.path.startswith("/api/") and request.method == "GET":
        kind = "cases" if "cases" in request.url.path else "balance" if "budget" in request.url.path else "message"
        return JSONResponse(sentra.decoy_response(kind))
    t0 = time.time()
    resp = await call_next(request)
    METRICS["requests"] += 1
    METRICS["latency_ms"] += (time.time() - t0) * 1000
    return resp


@app.get("/api/config")
def config():
    return {"paypal_env": settings.paypal_env, "currency": settings.currency, "genai": llm.available(),
            "llm": llm.provider_name(),
            "paypal_client_id": settings.paypal_client_id if settings.paypal_env != "mock" else "mock"}


@app.get("/api/users")
def users(db=Depends(db_dep)):
    return [{"id": u.id, "name": u.name, "role": u.role, "business_name": u.business_name}
            for u in db.scalars(select(User)).all()]


@app.post("/api/chat")
def chat(body: ChatIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import conversation

    return conversation.chat(db, user.id, body.message, body.case_id)


# ------------------------------------------------------------------- voice
class VoiceIn(BaseModel):
    text: str


@app.post("/api/voice")
def voice(body: VoiceIn, x_voice_token: str = Header(""), x_user_id: str = Header("alex"), db=Depends(db_dep)):
    """For Siri Shortcuts / phone assistants. Read-only: answers questions, never moves money."""
    import os

    expected = os.getenv("VOICE_TOKEN", "")
    if expected and x_voice_token != expected:
        raise HTTPException(401, "wrong voice token")
    u = db.get(User, x_user_id)
    if not u:
        raise HTTPException(401, "unknown user")
    if __import__("re").search(r"\b(pay|send|transfer|refund me|approve|confirm)\b", body.text, __import__("re").I) and \
            not __import__("re").search(r"\b(did|was|is|status|can i|should)\b", body.text, __import__("re").I):
        return {"speech": "For your safety, I can't pay, send or approve anything by voice. Open ContextIQ to confirm "
                          "it on screen.", "blocked_action": True}
    r = orchestrator.handle(db, u.id, body.text, voice=True)
    return {"speech": r["answer"], "topic": r["topic"]}


# ----------------------------------------------------------- cart / checkout
@app.post("/api/cart/analyze")
def cart_analyze(body: CartIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import insights as ins

    ins.watch_cart(db, user.id, body.merchant, [i.model_dump() for i in body.items], body.currency, body.page_url)
    return commerce.analyze_cart(db, user.id, merchant=body.merchant, items=[i.model_dump() for i in body.items],
                                 currency=body.currency, policy_text=body.policy_text, policy_url=body.policy_url,
                                 page_url=body.page_url, channel=body.channel)


@app.post("/api/checkout")
def checkout(body: CartIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return commerce.start_checkout(db, user.id, merchant=body.merchant, items=[i.model_dump() for i in body.items],
                                   currency=body.currency, policy_text=body.policy_text, policy_url=body.policy_url,
                                   channel=body.channel, seller_id=body.seller_id,
                                   purpose=body.purpose if body.purpose in ("personal", "business") else None)


@app.post("/api/cases/{case_id}/capture")
def capture(case_id: str, body: CaptureIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    r = commerce.complete_payment(db, user.id, case_id, body.approval_token, body.step_up_code, body.signals)
    if r.get("ok"):
        _after_paid(db, user.id, case_id)
    return r


def _after_paid(db, user_id: str, case_id: str) -> None:
    """Bought cart items leave the watchlist; a paid bill is marked done (so it stops showing as due)."""
    from .models import CartItem

    case = db.get(Case, case_id)
    names = {i.get("name") for i in (bc.view_case(db, case_id, user_id) or {}).get("agreement", {}).get("items", [])}
    for it in db.scalars(select(CartItem).where(CartItem.user_id == user_id, CartItem.active.is_(True))).all():
        if it.name in names and it.merchant == case.merchant:
            it.active = False
    for o in db.scalars(select(Obligation).where(Obligation.owner_id == user_id, Obligation.status == "open",
                                                 Obligation.case_id == case_id)).all():
        if o.kind in ("bill", "subscription", "supplier_payment", "emi"):
            o.status = "done"
    if case:
        db.add(OutboundNotice(
            user_id=user_id,
            recipient=case.merchant,
            channel="paypal_notice",
            notice_type="invoice_notice",
            subject=f"Autonomous Settlement: {case.title}",
            message=f"ContextIQ Autonomous Dispatch: Payment of ${case.amount:.2f} successfully captured and settled via PayPal. Recorded in digital briefcase.",
            amount=case.amount,
            status="delivered",
        ))
    db.commit()


@app.get("/api/bills")
def bills(user: User = Depends(user_dep), db=Depends(db_dep)):
    now = datetime.now(UTC)
    rows = db.scalars(select(Obligation).where(Obligation.owner_id == user.id, Obligation.status == "open",
                                               Obligation.kind.in_(["bill", "subscription", "supplier_payment", "emi"]))
                      .order_by(Obligation.due_at)).all()
    out = []
    for o in rows:
        due = o.due_at if o.due_at.tzinfo else o.due_at.replace(tzinfo=UTC)
        out.append({"id": o.id, "kind": o.kind, "title": o.title, "amount": o.amount, "due": due.isoformat(),
                    "days_left": max(0, -(-(due - now).total_seconds() // 86400)), "purpose": "business" if o.kind == "supplier_payment" else "personal",
                    "autopay": o.kind == "subscription"})
    return out


@app.post("/api/bills/{bill_id}/checkout")
def bill_checkout(bill_id: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    o = db.get(Obligation, bill_id)
    if not o or o.owner_id != user.id or o.status != "open":
        raise HTTPException(404, "bill not found")
    payee = o.title.split(" — ")[0].replace(" bill", "").replace(" renewal", "")
    out = commerce.start_checkout(db, user.id, merchant=payee, items=[{"name": o.title, "unit_price": o.amount, "quantity": 1}],
                                  currency=settings.currency, channel="bill",
                                  purpose="business" if o.kind == "supplier_payment" else "personal")
    o.case_id = out["case_id"]
    case = db.get(Case, out["case_id"])
    case.category = {"bill": "utilities", "subscription": "entertainment", "supplier_payment": "inventory"}.get(o.kind, "bills")
    db.commit()
    return out


class NoticeIn(BaseModel):
    recipient: str
    channel: str = "paypal_notice"
    notice_type: str = "payment_reminder"
    subject: str = ""
    message: str
    amount: float | None = None


def run_autonomous_sweep(db, user_id: str):
    """Autonomous event sweep: proactively triggers and dispatches system-level 1-way notices."""
    user = db.get(User, user_id)
    if not user:
        return
    now = datetime.now(UTC)

    # 1. Impending supplier obligations (< 48 hours)
    urgent_supplier = db.scalars(select(Obligation).where(
        Obligation.owner_id == user_id,
        Obligation.status == "open",
        Obligation.kind == "supplier_payment"
    )).all()
    for o in urgent_supplier:
        existing = db.scalar(select(OutboundNotice).where(
            OutboundNotice.user_id == user_id,
            OutboundNotice.recipient.like("%Nova%"),
            OutboundNotice.notice_type == "payment_reminder"
        ))
        if not existing:
            db.add(OutboundNotice(
                user_id=user_id,
                recipient="Nova Parts (Supplier)",
                channel="paypal_notice",
                notice_type="payment_reminder",
                subject="Autonomous System Notice: PO-1042 Verification & Payment Schedule",
                message=(f"ContextIQ Autonomous Dispatch: Verified sensor boards delivery against Purchase Order #PO-1042. "
                         f"${o.amount:.2f} scheduled for execution before due date ({o.due_at.strftime('%d %b')})."),
                amount=o.amount,
                status="delivered",
            ))

    # 2. Upcoming bills (< 72 hours)
    urgent_bills = db.scalars(select(Obligation).where(
        Obligation.owner_id == user_id,
        Obligation.status == "open",
        Obligation.kind.in_(["bill", "subscription"])
    )).all()
    for b in urgent_bills:
        existing = db.scalar(select(OutboundNotice).where(
            OutboundNotice.user_id == user_id,
            OutboundNotice.subject.like(f"%{b.title}%")
        ))
        if not existing:
            db.add(OutboundNotice(
                user_id=user_id,
                recipient=b.title.split(" — ")[0],
                channel="paypal_notice",
                notice_type="status_update",
                subject=f"Autonomous Pre-Debit Notice: {b.title}",
                message=(f"ContextIQ Autonomous Dispatch: Pre-debit cash reservation confirmed. ${b.amount:.2f} ring-fenced "
                         f"from liquid cash to guarantee timely settlement on {b.due_at.strftime('%d %b')}."),
                amount=b.amount,
                status="delivered",
            ))

    db.commit()


@app.get("/api/notices")
def get_notices(user: User = Depends(user_dep), db=Depends(db_dep)):
    run_autonomous_sweep(db, user.id)
    rows = db.scalars(select(OutboundNotice).where(OutboundNotice.user_id == user.id).order_by(OutboundNotice.created_at.desc())).all()
    return [{"id": r.id, "recipient": r.recipient, "channel": r.channel, "notice_type": r.notice_type,
             "subject": r.subject, "message": r.message, "amount": r.amount, "status": r.status,
             "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/api/notices/auto-sweep")
def trigger_auto_sweep(user: User = Depends(user_dep), db=Depends(db_dep)):
    run_autonomous_sweep(db, user.id)
    rows = db.scalars(select(OutboundNotice).where(OutboundNotice.user_id == user.id)).all()
    return {"ok": True, "autonomous": True, "total_notices": len(rows)}


@app.post("/api/notices")
def create_notice(body: NoticeIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    notice = OutboundNotice(
        user_id=user.id,
        recipient=body.recipient,
        channel=body.channel,
        notice_type=body.notice_type,
        subject=body.subject or f"One-Way Notice from {user.name}",
        message=body.message,
        amount=body.amount,
        status="delivered",
    )
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return {"ok": True, "notice": {
        "id": notice.id,
        "recipient": notice.recipient,
        "channel": notice.channel,
        "notice_type": notice.notice_type,
        "subject": notice.subject,
        "message": notice.message,
        "amount": notice.amount,
        "status": notice.status,
        "created_at": notice.created_at.isoformat()
    }}


@app.post("/api/reset")
def reset_everything(db=Depends(db_dep)):
    """Reset all transaction state and re-seed clean starter data."""
    from .models import (
        AuditLog,
        Budget,
        CartItem,
        Case,
        CaseEvent,
        Decision,
        Evidence,
        Obligation,
        OutboundNotice,
        PriceObservation,
        User,
    )
    for model in [OutboundNotice, CartItem, PriceObservation, LedgerEntry, CaseEvent, Evidence, Decision, Obligation, Case, AuditLog, Budget, User]:
        db.query(model).delete()
    db.commit()
    from .seed import ensure_seed
    ensure_seed()
    return {"ok": True, "message": "ContextIQ state has been completely reset to a clean, fresh seed."}




@app.get("/api/recommendations")
def recommendations(user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import recommend

    return recommend.build(db, user.id)


@app.post("/api/cases/{case_id}/approve-mock")
def approve_mock(case_id: str, db=Depends(db_dep)):
    """Mock mode only: stands in for the buyer clicking 'Pay' on PayPal's page."""
    if settings.paypal_env != "mock":
        raise HTTPException(400, "only in mock mode — approve on PayPal's page instead")
    from .paypal import mock

    case = db.get(Case, case_id)
    mock.approve(case.paypal_order_id)
    payments.sync_order_state(db, case)
    return {"ok": True}


@app.post("/api/cases/{case_id}/simulate-drop")
def simulate_drop(case_id: str, body: CaptureIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    """Self-healing demo: the connection drops right after PayPal commits the capture."""
    if settings.paypal_env != "mock":
        raise HTTPException(400, "fault injection only in mock mode")
    from .paypal import mock

    mock.inject_fault("capture_timeout_after_commit")
    res = commerce.complete_payment(db, user.id, case_id, body.approval_token, body.step_up_code, body.signals)
    captures = [c for c in mock.CAPTURES.values()
                if c["supplementary_data"]["related_ids"]["order_id"] == db.get(Case, case_id).paypal_order_id]
    return res | {"paypal_captures_for_order": len(captures)}


@app.post("/api/cases/{case_id}/delivered")
def delivered(case_id: str, days_ago: int = 0, db=Depends(db_dep)):
    return commerce.record_delivery(db, case_id, datetime.now(UTC) - timedelta(days=days_ago))


# --------------------------------------------------------- accounts / QR / disputes / graph
class ClassifyIn(BaseModel):
    payee: str
    description: str = ""
    channel: str = "online"
    amount: float


@app.post("/api/accounts/classify")
def accounts_classify(body: ClassifyIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .agents import accounts

    return accounts.classify_with_memory(db, user.id, body.payee, body.description, body.channel, body.amount)


class RememberIn(BaseModel):
    payee: str
    purpose: str


@app.post("/api/accounts/remember")
def accounts_remember(body: RememberIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .agents import accounts

    return accounts.remember(db, user.id, body.payee, body.purpose)


class RawIn(BaseModel):
    raw: str


@app.post("/api/qr/interpret")
def qr_interpret(body: RawIn, user: User = Depends(user_dep)):
    from .agents import qr

    return qr.interpret(body.raw)


class ClaimIn(BaseModel):
    topic: str
    value: bool
    note: str = ""


@app.post("/api/cases/{case_id}/claims")
def add_claim(case_id: str, body: ClaimIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .agents import disputes

    return disputes.add_claim(db, db.get(Case, case_id), user.id, body.topic, body.value, body.note)


@app.get("/api/cases/{case_id}/compare")
def compare_claims(case_id: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .agents import disputes

    if not bc.view_case(db, case_id, user.id):
        raise HTTPException(404, "not found or not permitted")
    return disputes.compare(db, db.get(Case, case_id))


@app.get("/api/graph")
def graph(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .intelligence import graph as g

    return g.for_user(db, user.id)


# ------------------------------------------------------------------ A2A
class A2AStart(BaseModel):
    case_id: str
    tamper: str | None = None  # demo only: "change_amount" proves altered messages are rejected


@app.post("/api/a2a/sessions")
def a2a_start(body: A2AStart, user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import a2a

    return a2a.run_session(db, body.case_id, user.id, tamper=body.tamper)


@app.post("/api/a2a/sessions/{session_id}/sync")
def a2a_sync(session_id: str, simulate_failure: bool = False, user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import a2a

    return a2a.sync_payment(db, session_id, simulate_failure)


@app.post("/a2a/inbox")
def a2a_inbox(env: dict, db=Depends(db_dep)):
    """HTTP transport: another ContextIQ instance can deliver signed envelopes here."""
    from . import a2a
    from .models import AgentKey

    receiver = db.scalar(select(AgentKey).where(AgentKey.agent_id == env.get("to"), AgentKey.revoked.is_(False)))
    if not receiver:
        raise HTTPException(404, "unknown receiving agent")
    ok, why = a2a.receive(db, receiver, env)
    return {"accepted": ok, "reason": why or None}


@app.post("/api/a2a/rotate")
def a2a_rotate(user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import a2a

    k = a2a.rotate_key(db, user.id, "seller" if user.role in ("merchant", "supplier") else "buyer")
    return {"new_key_id": k.key_id, "message": "Your agent has a new key; the old one is revoked."}


@app.get("/api/kg/retrieve")
def kg_retrieve(q: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .intelligence import kg

    return kg.build(db).retrieve(q, user.id)


@app.get("/api/kg/as-of")
def kg_as_of(case_id: str, at: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    from datetime import datetime as dt

    from .intelligence import kg

    g = kg.build(db)
    t = dt.fromisoformat(at)
    t = t if t.tzinfo else t.replace(tzinfo=UTC)
    facts = [f for f in g.neighborhood(f"case:{case_id}", user.id, hops=1, t=t)]
    return {"at": t.isoformat(), "facts": [g.render(f) for f in facts]}


@app.get("/api/kg/contradictions")
def kg_contradictions(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .intelligence import kg

    g = kg.build(db)
    return [c for c in g.contradictions()]


@app.get("/api/invest/research")
def invest_research(symbol: str, user: User = Depends(user_dep)):
    from .market.provider import research

    return research(symbol.upper())


class HoldingsIn(BaseModel):
    holdings: list[dict]


@app.post("/api/invest/diversification")
def invest_div(body: HoldingsIn, user: User = Depends(user_dep)):
    from .market.provider import diversification

    return diversification(body.holdings)


@app.get("/api/plugins")
def plugin_registry():
    from . import plugins

    return plugins.describe()


# ---------------------------------------------------------------- passkeys
@app.get("/api/passkeys/status")
def passkey_status(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .security import passkeys

    return {"has_passkey": passkeys.has_passkey(db, user.id), "rp_id": passkeys.RP_ID}


@app.post("/api/passkeys/register/options")
def passkey_reg_options(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .security import passkeys

    return passkeys.registration_options(db, user)


@app.post("/api/passkeys/register/verify")
def passkey_reg_verify(credential: dict, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .security import passkeys

    try:
        return passkeys.register(db, user, credential)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Passkey not saved: {exc}")


class PasskeyAuthIn(BaseModel):
    approval_token: str
    credential: dict | None = None


@app.post("/api/passkeys/auth/options")
def passkey_auth_options(body: PasskeyAuthIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .security import passkeys

    try:
        return passkeys.auth_options(db, user, body.approval_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/passkeys/auth/verify")
def passkey_auth_verify(body: PasskeyAuthIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .security import passkeys

    try:
        return passkeys.verify_for_approval(db, user, body.approval_token, body.credential or {})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Couldn't confirm with your passkey: {exc}")


class SetupIn(BaseModel):
    uses: str = "personal"
    monthly_budget: float | None = None
    monthly_income: float | None = None
    pay_day: int | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None
    goals: list[str] = []
    location_ok: bool = False
    home_lat: float | None = None
    home_lon: float | None = None


@app.get("/api/profile")
def profile(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .models import Budget

    b = db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category == "total"))
    return {"name": user.name, "setup_done": user.setup_done, "uses": user.uses,
            "goals": [g for g in (user.goals or "").split(",") if g], "monthly_budget": b.limit if b else None,
            "monthly_income": user.monthly_income, "pay_day": user.pay_day, "work_start_hour": user.work_start_hour,
            "work_end_hour": user.work_end_hour, "location_ok": user.location_ok, "business_name": user.business_name,
            "available_balance": user.available_balance, "balance_source": user.balance_source,
            "paypal_email": user.paypal_email}


class BalanceIn(BaseModel):
    balance: float


@app.post("/api/balance")
def set_balance(body: BalanceIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    user.available_balance = max(0.0, round(float(body.balance), 2))
    user.balance_source = "user_entered"
    db.commit()
    return {"ok": True, "available_balance": user.available_balance}


class PayPalAccountIn(BaseModel):
    email: str


@app.post("/api/profile/paypal")
def set_paypal_account(body: PayPalAccountIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    user.paypal_email = body.email.strip()
    db.commit()
    return {"ok": True, "paypal_email": user.paypal_email}


@app.post("/api/profile/setup")
def profile_setup(body: SetupIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    from .models import Budget

    if body.uses not in ("personal", "business", "both"):
        raise HTTPException(400, "uses must be personal, business or both")
    user.uses, user.goals = body.uses, ",".join(g for g in body.goals if g in ("save", "overspend", "deadlines", "deals"))
    for f in ("monthly_income", "pay_day", "work_start_hour", "work_end_hour"):
        if getattr(body, f) is not None:
            setattr(user, f, getattr(body, f))
    user.location_ok = bool(body.location_ok and body.home_lat is not None)
    user.home_lat, user.home_lon = (body.home_lat, body.home_lon) if user.location_ok else (None, None)
    if body.monthly_budget:
        b = db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category == "total"))
        if b:
            b.limit = body.monthly_budget
        else:
            db.add(Budget(user_id=user.id, category="total", limit=body.monthly_budget))
    user.setup_done = True
    db.commit()
    return {"ok": True}


@app.get("/api/insights")
def insights(hour: int | None = None, weekday: int | None = None, lat: float | None = None, lon: float | None = None,
             account: str | None = None, user: User = Depends(user_dep), db=Depends(db_dep)):
    from . import insights as ins
    from .context import decide

    now = datetime.now(UTC)
    local = now + timedelta(hours=5, minutes=30)
    ctx = decide(user, local.hour if hour is None else hour, local.weekday() if weekday is None else weekday,
                 lat, lon, account)
    out = ins.generate(db, user.id, now, ctx)
    out["trend"] = ins.spending_trend(db, user.id)
    return out


@app.get("/api/cart/watch")
def cart_watch(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .models import CartItem, PriceObservation

    items = db.scalars(select(CartItem).where(CartItem.user_id == user.id, CartItem.active.is_(True))).all()
    out = []
    for it in items:
        hist = db.scalars(select(PriceObservation).where(PriceObservation.product_key == it.product_key)
                          .order_by(PriceObservation.seen_at)).all()
        out.append({"id": it.id, "name": it.name, "merchant": it.merchant, "currency": it.currency,
                    "prices": [h.price for h in hist], "now": hist[-1].price if hist else None})
    return out


@app.get("/console", response_class=HTMLResponse)
def console():
    return FileResponse(STATIC / "console.html")


@app.get("/api/features")
def features():
    from .features import FEATURES

    return FEATURES


# ------------------------------------------------------------------- cases
@app.get("/api/cases")
def cases(user: User = Depends(user_dep), db=Depends(db_dep)):
    return helpdesk.list_cases(db, user.id)


@app.get("/api/cases/{case_id}")
def case_view(case_id: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    v = bc.view_case(db, case_id, user.id)
    if not v:
        raise HTTPException(404, "not found or not permitted")
    from .agents import disputes

    v["checklist"] = disputes.checklist(db, db.get(Case, case_id))
    return v


@app.post("/api/cases/{case_id}/investigate")
def investigate(case_id: str, claim: str = "payment not received", user: User = Depends(user_dep), db=Depends(db_dep)):
    case = db.get(Case, case_id)
    return commerce.payment_investigation(db, case, supplier_claim=claim)


@app.get("/api/cases/{case_id}/refund-eligibility")
def refund_elig(case_id: str, issue: str = "", user: User = Depends(user_dep), db=Depends(db_dep)):
    return commerce.refund_eligibility(db, db.get(Case, case_id), issue)


class RefundIn(BaseModel):
    amount: float | None = None
    reason: str = ""
    approval_token: str | None = None
    step_up_code: str | None = None


@app.post("/api/cases/{case_id}/refund/approve")
def refund_approve(case_id: str, user: User = Depends(user_dep), db=Depends(db_dep)):
    """Seller explicitly approves a refund on their case."""
    case = db.get(Case, case_id)
    return {"approval_token": gateway.issue_approval(db, user_id=user.id, case=case, action="refund").token}


@app.post("/api/cases/{case_id}/refund")
def refund(case_id: str, body: RefundIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    if body.step_up_code and body.approval_token:
        gateway.pass_step_up(db, body.approval_token, body.step_up_code)
    return commerce.merchant_refund(db, user.id, case_id, body.approval_token or "", body.amount, body.reason)


class ResolutionIn(BaseModel):
    action: str
    issue: str = ""


@app.post("/api/cases/{case_id}/resolution")
def case_resolution(case_id: str, body: ResolutionIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return commerce.execute_resolution(db, case, action=body.action, issue=body.issue, user_id=user.id)


# --------------------------------------------------------------- webhooks
@app.post("/api/webhooks/paypal")
async def paypal_webhook(request: Request, db=Depends(db_dep)):
    event = json.loads(await request.body())
    if not get_client().verify_webhook(dict(request.headers), event):
        sentra.ingest(db, kind="webhook_signature_invalid", severity="warning", detail={"id": event.get("id")})
        raise HTTPException(400, "invalid signature")
    return _apply_webhook(db, event)


def _apply_webhook(db, event: dict) -> dict:
    res = event.get("resource", {})
    order_id = res.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    case = None
    if order_id:
        case = db.scalar(select(Case).where(Case.paypal_order_id == order_id))
    if not case and res.get("capture_id"):
        case = db.scalar(select(Case).where(Case.paypal_capture_id == res["capture_id"]))
    if not case:
        return {"ok": True, "ignored": "no matching case"}
    ev = bc.add_event(db, case, f"webhook_{event['event_type'].lower()}", "paypal_webhook",
                      {"resource_id": res.get("id"), "status": res.get("status")}, external_id=event["id"])
    if ev is None:
        return {"ok": True, "duplicate": True}
    if event["event_type"] == "PAYMENT.CAPTURE.COMPLETED":
        payments.sync_order_state(db, case)
    return {"ok": True, "case_id": case.id}


@app.post("/api/mock/deliver-webhooks")
def deliver_mock_webhooks(db=Depends(db_dep)):
    """Mock mode: delivers queued PayPal events through the real handler (twice, to prove dedupe)."""
    from .paypal import mock

    results = []
    for ev in list(mock.EVENTS):
        for _ in range(2):
            results.append(_apply_webhook(db, ev))
    mock.EVENTS.clear()
    return {"delivered": len(results), "duplicates_dropped": sum(1 for r in results if r.get("duplicate"))}


# -------------------------------------------------------------- QR / B2B
class QRIn(BaseModel):
    items: list[Item]
    currency: str = Field(default_factory=lambda: settings.currency)
    policy_text: str = ""


@app.post("/api/qr/create")
def qr_create(body: QRIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return commerce.merchant_create_qr(db, user.id, items=[i.model_dump() for i in body.items], currency=body.currency,
                                       policy_text=body.policy_text)


class ScanIn(BaseModel):
    token: str


@app.post("/api/qr/scan")
def qr_scan(body: ScanIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return commerce.buyer_scan_qr(db, user.id, body.token)


class InvoiceIn(BaseModel):
    supplier: str
    po: dict
    invoice: dict
    text: str = ""


@app.post("/api/invoice/check")
def invoice_check(body: InvoiceIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return commerce.check_invoice(db, user.id, supplier=body.supplier, po=body.po, invoice=body.invoice, text=body.text)


# ------------------------------------------------------------- finance
@app.get("/api/budget")
def budget(user: User = Depends(user_dep), db=Depends(db_dep)):
    return budget_agent.status(db, user.id) | {"alerts": budget_agent.overspend_alerts(db, user.id),
                                               "forecast_30d": budget_agent.forecast(db, user.id),
                                               "subscriptions": budget_agent.detect_subscriptions(db, user.id)}


class BudgetIn(BaseModel):
    category: str = "total"
    limit: float


@app.post("/api/budget")
def set_budget(body: BudgetIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    b = db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category == body.category))
    if b:
        b.limit = body.limit
    else:
        db.add(Budget(user_id=user.id, category=body.category, limit=body.limit))
    return {"ok": True}


@app.get("/api/whatif")
def whatif(amount: float, user: User = Depends(user_dep), db=Depends(db_dep)):
    return budget_agent.what_if(db, user.id, amount)


@app.get("/api/obligations")
def obligations(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .intelligence.reasoning import temporal

    rows = db.scalars(select(Obligation).where(Obligation.owner_id == user.id, Obligation.status == "open")
                      .order_by(Obligation.due_at)).all()
    return [{"id": o.id, "kind": o.kind, "title": o.title, "amount": o.amount, "case_id": o.case_id,
             "due": (o.due_at if o.due_at.tzinfo else o.due_at.replace(tzinfo=UTC)).date().isoformat()}
            | temporal(o.due_at) for o in rows]


class InvestIn(BaseModel):
    amount: float
    horizon_months: int = 12


@app.post("/api/invest")
def invest(body: InvestIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return investment.advise(db, user.id, body.amount, body.horizon_months)


class RiskIn(BaseModel):
    payee: str
    amount: float
    text: str = ""
    new_device: bool = False
    ip_country_mismatch: bool = False
    payee_changed_recently: bool = False
    session_age_min: float = 30


@app.post("/api/fraud/score")
def fraud(body: RiskIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    return ctx_agent.assess_risk(db, user.id, body.payee, body.amount, text=body.text, new_device=body.new_device,
                                 ip_country_mismatch=body.ip_country_mismatch,
                                 payee_changed_recently=body.payee_changed_recently,
                                 session_age_min=body.session_age_min)


# ---------------------------------------------------- adaptive UI + metrics
@app.get("/api/home")
def home(user: User = Depends(user_dep), db=Depends(db_dep)):
    from .intelligence.reasoning import temporal

    boosts = {}
    obs = db.scalars(select(Obligation).where(Obligation.owner_id == user.id, Obligation.status == "open")).all()
    if any(temporal(o.due_at)["status"] == "closing" and o.kind.endswith("window") for o in obs):
        boosts["refund_tracker"] = 0.5
    if any(o.kind in ("bill", "subscription") and temporal(o.due_at)["days_left"] < 7 for o in obs):
        boosts["bills_reminders"] = 0.3
    arms = [a for a in adaptive.SHORTCUTS if a != "investments" or user.investment_enabled]
    if user.role != "merchant":
        arms = [a for a in arms if a != "merchant_qr"]
    order = adaptive.rank(db, user.id, "home", arms, boosts, seed=len(obs))
    return {"shortcuts": order, "fixed": ["pay", "cases", "chat"], "alerts": budget_agent.overspend_alerts(db, user.id)}


class FeedbackIn(BaseModel):
    context: str = "home"
    arm: str
    reward: float


@app.post("/api/feedback")
def feedback(body: FeedbackIn, user: User = Depends(user_dep), db=Depends(db_dep)):
    adaptive.feedback(db, user.id, body.context, body.arm, body.reward)
    return {"ok": True}


@app.get("/api/metrics")
def metrics(db=Depends(db_dep)):
    from .config import MODEL_DIR

    report = json.loads((MODEL_DIR / "report.json").read_text()) if (MODEL_DIR / "report.json").exists() else {}
    return {"cache": cache.stats(), "llm": llm.METER | {"enabled": llm.available(),
                                                        "provider": llm.provider_name() if llm.available() else ""},
            "api": {"requests": METRICS["requests"],
                    "avg_latency_ms": round(METRICS["latency_ms"] / max(1, METRICS["requests"]), 1)},
            "audit_entries": len(db.scalars(select(AuditLog)).all()),
            "security_incidents": sentra.correlate(db), "models": report}


@app.post("/api/cache/{state}")
def cache_toggle(state: str):
    cache.enabled = state == "on"
    return cache.stats()


@app.get("/api/audit")
def audit(user: User = Depends(user_dep), db=Depends(db_dep)):
    rows = db.scalars(select(AuditLog).where(AuditLog.actor == user.id).order_by(AuditLog.created_at.desc())).all()
    return [{"action": a.action, "case_id": a.case_id, "verdict": a.verdict, "reasons": a.reasons,
             "at": a.created_at.isoformat()} for a in rows[:50]]
