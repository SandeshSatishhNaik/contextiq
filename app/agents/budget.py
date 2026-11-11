"""Financial intelligence expert: budgets, what-if, obligations, subscriptions, forecast.

Works only with data ContextIQ can see (its own payments + what the user entered) and says how
much that covers. Never invents a balance for an unconnected account.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..fmt import money
from ..intelligence.reasoning import counterfactual
from ..ml import runtime
from ..models import Budget, LedgerEntry, Obligation, User


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_payday(user: User, now: datetime) -> datetime:
    day = min(max(user.pay_day, 1), 28)
    d = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    if d <= now:
        d = (d + timedelta(days=32)).replace(day=day)
    return d


BUSINESS_KINDS = {"supplier_payment"}


def status(db: Session, user_id: str, now: datetime | None = None, purpose: str = "personal") -> dict:
    now = now or datetime.now(UTC)
    user = db.get(User, user_id)
    start = _month_start(now)
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id)).all()
    month = [e for e in entries if _aware(e.occurred_at) >= start and e.amount > 0 and e.purpose == purpose]
    by_cat: dict[str, float] = defaultdict(float)
    for e in month:
        by_cat[e.category] += e.amount
    spent = round(sum(by_cat.values()), 2)
    budgets = db.scalars(select(Budget).where(Budget.user_id == user_id)).all()
    total_limit = next((b.limit for b in budgets if b.category == "total"), None)
    payday = _next_payday(user, now) if user else now + timedelta(days=30)
    upcoming = db.scalars(select(Obligation).where(Obligation.owner_id == user_id, Obligation.status == "open",
                                                   Obligation.direction == "out")).all()
    upcoming = [o for o in upcoming if (o.kind in BUSINESS_KINDS) == (purpose == "business")]
    due_before_payday = [o for o in upcoming if _aware(o.due_at) <= payday and o.amount > 0]
    bills_total = round(sum(o.amount for o in due_before_payday), 2)
    avail_bal = user.available_balance if user else None
    free_cash = round(avail_bal - bills_total, 2) if avail_bal is not None else None
    sources = {e.source for e in entries}
    return {
        "month_spent": spent, "by_category": {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
        "total_budget": total_limit, "remaining": None if total_limit is None else round(total_limit - spent, 2),
        "category_budgets": {b.category: b.limit for b in budgets if b.category != "total"},
        "bills_before_payday": [{"title": o.title, "amount": o.amount, "due": _aware(o.due_at).date().isoformat()}
                                for o in sorted(due_before_payday, key=lambda o: o.due_at)],
        "bills_total": bills_total,
        "free_cash": free_cash,
        "monthly_income": user.monthly_income if user else None,
        "pay_day": user.pay_day if user else None,
        "next_payday": payday.date().isoformat(),
        "available_balance": avail_bal,
        "balance_source": user.balance_source if user else "unknown",
        "coverage_note": ("Based on ContextIQ payments and the bills and balance you entered. "
                          "Accounts that aren't connected are not included."),
        "data_sources": sorted(sources),
    }


def what_if(db: Session, user_id: str, amount: float, label: str = "this purchase",
            now: datetime | None = None, purpose: str = "personal") -> dict:
    """Counterfactual: buy now vs wait until payday, on budget and on cash."""
    now = now or datetime.now(UTC)
    s = status(db, user_id, now, purpose)
    bills = sum(b["amount"] for b in s["bills_before_payday"])
    state = {"remaining": s["remaining"], "balance": s["available_balance"], "bills": bills, "amount": amount}

    def buy_now(st):
        out = {}
        if st["remaining"] is not None:
            out["budget_left"] = round(st["remaining"] - st["bills"] - st["amount"], 2)
        if st["balance"] is not None:
            out["cash_left_before_payday"] = round(st["balance"] - st["bills"] - st["amount"], 2)
        return out

    def wait(st):
        out = {}
        if st["remaining"] is not None:
            out["budget_left"] = round(st["remaining"] - st["bills"], 2)
        if st["balance"] is not None:
            out["cash_left_before_payday"] = round(st["balance"] - st["bills"], 2)
        return out

    outcomes = counterfactual(state, {"buy_now": buy_now, "wait_until_payday": wait})
    now_out = outcomes["buy_now"]
    shortfall = min([v for v in now_out.values()] or [0])
    if not now_out:
        verdict, message = "unknown", "Set a budget or enter your balance and I can tell you whether this fits."
    elif shortfall < 0:
        verdict = "wait"
        message = (f"If you buy {label} now, you'd be {money(abs(shortfall))} short once your "
                   f"{len(s['bills_before_payday'])} upcoming bill(s) are paid. Waiting until payday "
                   f"({s['next_payday']}) keeps you covered — but it's your call.")
    elif shortfall < 50:
        verdict = "ok"
        message = (f"You can afford {label}, but it's tight: only {money(shortfall)} would be left after your "
                   "upcoming bills.")
    else:
        verdict = "ok"
        message = f"Yes, you can afford {label}. You'd still have {money(shortfall)} left after your upcoming bills."
    return {"verdict": verdict, "message": message, "outcomes": outcomes, "bills_before_payday": s["bills_before_payday"],
            "next_payday": s["next_payday"], "coverage_note": s["coverage_note"]}


def detect_subscriptions(db: Session, user_id: str) -> list[dict]:
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0)).all()
    by_payee: dict[str, list[LedgerEntry]] = defaultdict(list)
    for e in entries:
        by_payee[e.payee].append(e)
    subs = []
    for payee, es in by_payee.items():
        es.sort(key=lambda e: e.occurred_at)
        t0 = _aware(es[0].occurred_at)
        days = [(_aware(e.occurred_at) - t0).total_seconds() / 86400 for e in es]
        ok, p = runtime.is_subscription(days, [e.amount for e in es])
        if ok:
            gap = (days[-1] - days[0]) / max(1, len(days) - 1)
            nxt = _aware(es[-1].occurred_at) + timedelta(days=gap)
            subs.append({"payee": payee, "amount": es[-1].amount, "every_days": round(gap),
                         "next_expected": nxt.date().isoformat(), "confidence": p, "payments_seen": len(es)})
    return sorted(subs, key=lambda s: s["next_expected"])


def forecast(db: Session, user_id: str, horizon: int = 30) -> dict:
    f = runtime.forecaster()
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0)).all()
    if entries:
        s = pd.Series({_aware(e.occurred_at).date(): 0.0 for e in entries})
        for e in entries:
            s[_aware(e.occurred_at).date()] += e.amount
        idx = pd.date_range(min(s.index), max(s.index))
        s = s.reindex(idx.date, fill_value=0.0)
        s.index = pd.to_datetime(s.index)
        f.fit_ledger(user_id, s)
    fc = f.forecast_user(user_id, horizon=horizon, start_weekday=datetime.now(UTC).weekday())
    fc["note"] = "Range, not a promise: P10–P90 of simulated spending."
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in fc.items()}


def overspend_alerts(db: Session, user_id: str) -> list[str]:
    s = status(db, user_id)
    alerts = []
    if s["total_budget"]:
        used = s["month_spent"] / s["total_budget"]
        if used >= 0.8:
            alerts.append(f"Heads up: you've used {used:.0%} of this month's budget.")
    for cat, lim in s["category_budgets"].items():
        spent = s["by_category"].get(cat, 0)
        if lim and spent >= 0.8 * lim:
            alerts.append(f"{cat.title()} is at {money(spent)} of its {money(lim)} limit.")
    return alerts


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
