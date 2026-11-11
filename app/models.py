"""Transaction briefcase and supporting tables.

`case_events` is the append-only source of truth. Provenance on evidence is one of
verified (PayPal API / verified webhook / signed agreement), claimed (a person said it)
or inferred (an AI/model conclusion, which must cite evidence ids).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex[:16]


def now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="shopper")  # shopper | merchant | supplier
    business_name: Mapped[str | None] = mapped_column(String, nullable=True)
    work_start_hour: Mapped[int] = mapped_column(Integer, default=9)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=17)
    monthly_income: Mapped[float] = mapped_column(Float, default=0)
    pay_day: Mapped[int] = mapped_column(Integer, default=1)
    available_balance: Mapped[float | None] = mapped_column(Float, nullable=True)  # user-entered unless connected
    balance_source: Mapped[str] = mapped_column(String, default="user_entered")
    risk_tolerance: Mapped[str] = mapped_column(String, default="moderate")
    investment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paypal_email: Mapped[str | None] = mapped_column(String, nullable=True)
    # personalization (set once in the 3-step setup; never asked again)
    setup_done: Mapped[bool] = mapped_column(Boolean, default=False)
    uses: Mapped[str] = mapped_column(String, default="personal")  # personal | business | both
    goals: Mapped[str] = mapped_column(String, default="")  # comma list: save,overspend,deadlines,deals
    home_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_ok: Mapped[bool] = mapped_column(Boolean, default=False)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String, index=True)
    counterparty_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String)
    merchant: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String, default="online")  # online | in_person | invoice
    purpose: Mapped[str] = mapped_column(String, default="personal")  # personal | business
    category: Mapped[str] = mapped_column(String, default="general")
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="USD")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|active|monitoring|resolved|archived
    payment_state: Mapped[str] = mapped_column(String, default="intent_recorded")
    paypal_order_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    rev: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    type: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)  # paypal_api | paypal_webhook | user | merchant | system | ai
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Agreement(Base):
    __tablename__ = "agreements"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String)
    payee: Mapped[str] = mapped_column(String)
    terms: Mapped[dict] = mapped_column(JSON, default=dict)
    signed_hash: Mapped[str] = mapped_column(String)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    provenance: Mapped[str] = mapped_column(String)  # verified | claimed | inferred
    summary: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String)
    cites: Mapped[list] = mapped_column(JSON, default=list)  # evidence ids an inference rests on
    visible_to: Mapped[str] = mapped_column(String, default="both")  # buyer | seller | both
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PolicySnapshot(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    merchant: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String, default="")
    content_hash: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str] = mapped_column(Text)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Obligation(Base):
    __tablename__ = "obligations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String)  # return_window | warranty | bill | subscription | supplier_payment | delivery | emi
    title: Mapped[str] = mapped_column(String)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[float] = mapped_column(Float, default=0)
    direction: Mapped[str] = mapped_column(String, default="out")  # out | in
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="open")  # open | done | missed | cancelled


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    chosen: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("case_id", "party_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    party_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # buyer | seller


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    verdict: Mapped[str] = mapped_column(String)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)  # "total" or a category
    period: Mapped[str] = mapped_column(String, default="monthly")
    limit: Mapped[float] = mapped_column(Float)


class LedgerEntry(Base):
    """Spending/income ContextIQ can see (its own payments + user-entered items)."""
    __tablename__ = "ledger"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payee: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="general")
    purpose: Mapped[str] = mapped_column(String, default="personal")
    amount: Mapped[float] = mapped_column(Float)  # positive = spend, negative = income
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source: Mapped[str] = mapped_column(String, default="contextiq")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    product_key: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    merchant: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="USD")
    url: Mapped[str] = mapped_column(String, default="")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UsedNonce(Base):
    __tablename__ = "used_nonces"
    value: Mapped[str] = mapped_column(String, primary_key=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Approval(Base):
    __tablename__ = "approvals"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    case_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    payee: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    step_up_code: Mapped[str | None] = mapped_column(String, nullable=True)
    step_up_passed: Mapped[bool] = mapped_column(Boolean, default=False)


class BanditArm(Base):
    __tablename__ = "bandit_arms"
    __table_args__ = (UniqueConstraint("user_id", "context", "arm"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    context: Mapped[str] = mapped_column(String)
    arm: Mapped[str] = mapped_column(String)
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)


class SecurityEvent(Base):
    """SENTRA-style security telemetry: ingested, correlated, kept as evidence."""
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, default="info")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PayeePreference(Base):
    """Remembered personal/business choice per payee, so ContextIQ stops asking once the user has answered."""
    __tablename__ = "payee_preferences"
    __table_args__ = (UniqueConstraint("user_id", "payee"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    payee: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)  # personal | business
    times_confirmed: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentKey(Base):
    """Trusted key registry for agent identities (supports rotation and revocation)."""
    __tablename__ = "agent_keys"
    key_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    party_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # buyer | seller
    private_pem: Mapped[str] = mapped_column(Text)  # demo: stored server-side; in production it stays on the party's device
    public_b64: Mapped[str] = mapped_column(String)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class A2ASession(Base):
    __tablename__ = "a2a_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(String, index=True)
    buyer_agent: Mapped[str] = mapped_column(String)
    seller_agent: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="hello_sent")  # hello_sent|accepted|context_exchanged|compared|synced|closed|rejected
    sync_state: Mapped[str] = mapped_column(String, default="not_synced")  # independent of the PayPal payment state
    findings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class A2AMessage(Base):
    __tablename__ = "a2a_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    sender: Mapped[str] = mapped_column(String)
    receiver: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    envelope: Mapped[dict] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Invoice(Base):
    """A seller's invoice for a case (what the seller's agent shares)."""
    __tablename__ = "invoices"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(String, index=True)
    seller_id: Mapped[str] = mapped_column(String)
    items: Mapped[list] = mapped_column(JSON, default=list)
    paypal_invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Passkey(Base):
    __tablename__ = "passkeys"
    credential_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CartItem(Base):
    """Items the user has in a cart (read by the extension when they click it, or added from the demo store).
    ContextIQ watches their price and checks each drop against the user's budget."""
    __tablename__ = "cart_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    merchant: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    product_key: Mapped[str] = mapped_column(String, index=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    url: Mapped[str] = mapped_column(String, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OutboundNotice(Base):
    """One-way communication sent to suppliers, customers, or contacts."""
    __tablename__ = "outbound_notices"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    recipient: Mapped[str] = mapped_column(String)  # name, email, or company
    channel: Mapped[str] = mapped_column(String, default="paypal_notice")  # email | sms | paypal_notice
    notice_type: Mapped[str] = mapped_column(String, default="payment_reminder")  # payment_reminder | invoice_notice | payment_request | announcement
    subject: Mapped[str] = mapped_column(String, default="")
    message: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="delivered")  # sent | delivered
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

