"""Proactive insights: ContextIQ tells the user what matters without being asked.

Each card has a priority, a short title, a plain-language body, the numbers behind it (for visuals)
and at most one suggested action. Nothing here moves money; actions open the right screen.
"""
from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents import budget as budget_agent
from .fmt import days as fdays
from .fmt import money
from .intelligence.reasoning import temporal
from .models import CartItem, Case, LedgerEntry, Obligation, PriceObservation, User

PRIORITY = {"urgent": 0, "money": 1, "tip": 2, "good": 3}


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _deadlines(db: Session, user_id: str, now: datetime) -> list[dict]:
    out = []
    obs = db.scalars(select(Obligation).where(Obligation.owner_id == user_id, Obligation.status == "open",
                                              Obligation.case_id.is_not(None))).all()
    label = {"return_window": "return it", "replacement_window": "swap it free if it's faulty", "warranty": "claim warranty"}
    for o in obs:
        if o.kind not in label:
            continue
        t = temporal(o.due_at, now)
        if t["status"] == "expired" or t["days_left"] > (30 if o.kind == "warranty" else 10):
            continue
        case = db.get(Case, o.case_id)
        out.append({"id": f"dl-{o.id}", "kind": "deadline", "priority": "urgent" if t["days_left"] <= 3 else "money",
                    "title": f"{fdays(t['days_left'])} left to {label[o.kind]}",
                    "body": f"{case.title} from {case.merchant}. The window closes on {_aware(o.due_at):%d %b}.",
                    "numbers": {"days_left": max(0, round(t["days_left"])), "window_days": _window(o, case)},
                    "action": {"label": "See options", "go": "activity", "case_id": case.id}})
    return out


def _window(o: Obligation, case: Case) -> int:
    return max(1, round((_aware(o.due_at) - _aware(case.created_at)).total_seconds() / 86400))


def _price_drops(db: Session, user_id: str, now: datetime) -> list[dict]:
    out = []
    for it in db.scalars(select(CartItem).where(CartItem.user_id == user_id, CartItem.active.is_(True))).all():
        hist = db.scalars(select(PriceObservation).where(PriceObservation.product_key == it.product_key)
                          .order_by(PriceObservation.seen_at)).all()
        if len(hist) < 2:
            continue
        prices = [h.price for h in hist]
        now_p, before = prices[-1], max(prices[:-1])
        if now_p >= before - 0.005:
            continue
        lowest = now_p <= min(prices)
        w = budget_agent.what_if(db, user_id, now_p, label=f"the {it.name}")
        pace_over = _pace(db, user_id, now)["over"]
        cash_ok = w["verdict"] == "ok"
        fits = cash_ok and pace_over + now_p <= 0
        body = (f"Now {money(now_p, it.currency)}, down from {money(before, it.currency)}"
                f"{' — the lowest price seen' if lowest and len(prices) >= 3 else ''}. ")
        body += ("It fits your budget, with " + w["message"].split("You'd still have ")[-1] if fits and "You'd still have" in w["message"]
                 else "It fits your budget." if fits else
                 f"Your balance can cover it, but this month's budget can't — keep it in the cart; it may drop again, and payday is "
                 f"{datetime.fromisoformat(w['next_payday']):%d %b}." if cash_ok else
                 f"But buying now would leave you short before payday — waiting until payday ({datetime.fromisoformat(w['next_payday']):%d %b}) keeps you covered.")
        out.append({"id": f"pd-{it.id}", "kind": "price_drop", "priority": "money" if fits else "tip",
                    "title": f"Price drop: {it.name} −{round((1 - now_p / before) * 100)}%",
                    "body": body.strip(), "numbers": {"history": prices[-8:], "now": now_p, "before": before,
                                                      "saving": round(before - now_p, 2), "fits_budget": fits},
                    "action": {"label": "Check and buy" if fits else "Remind me on payday", "go": "pay", "cart_item": it.id}})
    return out


def _pace(db: Session, user_id: str, now: datetime) -> dict:
    """Month-end projection from everyday spending (< $100 items); one-off big buys are counted once."""
    s = budget_agent.status(db, user_id, now)
    dim = calendar.monthrange(now.year, now.month)[1]
    elapsed, days_left = max(1, now.day), dim - now.day
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = [r for r in db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0,
                                                             LedgerEntry.purpose == "personal")).all()
            if _aware(r.occurred_at) >= month_start]
    everyday = [r for r in rows if r.amount < 100]
    rate = sum(r.amount for r in everyday) / elapsed
    projected = s["month_spent"] + rate * days_left
    per_cat: dict[str, float] = {}
    for r in everyday:
        per_cat[r.category] = per_cat.get(r.category, 0) + r.amount
    over = projected - s["total_budget"] if s["total_budget"] else 0
    return {"status": s, "rate": rate, "projected": projected, "over": over, "days_left": days_left,
            "elapsed": elapsed, "per_cat": per_cat}


def _budget(db: Session, user_id: str, now: datetime) -> list[dict]:
    s = budget_agent.status(db, user_id, now)
    out = []
    if s["total_budget"]:
        pc = _pace(db, user_id, now)
        rate, projected, over, days_left, elapsed, everyday_cat = (pc["rate"], pc["projected"], pc["over"], pc["days_left"],
                                                                   pc["elapsed"], pc["per_cat"])
        if over > 0:
            disc = {k: v for k, v in everyday_cat.items() if k in ("dining", "clothing", "entertainment", "shopping", "transport", "groceries")}
            cat = max(disc, key=disc.get) if disc else None
            weeks = max(1.0, days_left / 7)
            weekly_now = disc.get(cat, 0) / elapsed * 7 if cat else 0
            weekly_cut = min(over / weeks, weekly_now * 0.6) if cat else 0
            fixes = weekly_cut * weeks >= over * 0.95
            out.append({"id": "budget-pace", "kind": "budget", "priority": "money",
                        "title": f"Heading {money(over)} over budget",
                        "body": (f"You've spent {money(s['month_spent'])} of {money(s['total_budget'])} and everyday spending runs about "
                                 f"{money(rate)} a day. "
                                 + (f"Spending {money(weekly_cut)} less a week on {cat} " + ("closes the gap." if fixes else "gets you most of the way.")
                                    if cat and weekly_cut >= 5 else "Holding off on non-essentials until payday keeps it in check.")),
                        "numbers": {"spent": s["month_spent"], "budget": s["total_budget"], "projected": round(projected, 2),
                                    "cut_category": cat, "weekly_cut": round(weekly_cut, 2)},
                        "action": {"label": "See spending", "go": "activity"}})
        else:
            spare = -over
            out.append({"id": "budget-pace", "kind": "budget", "priority": "good",
                        "title": "You're on track this month",
                        "body": f"About {money(spare)} should be left at month end. Putting {money(spare * 0.5)} into savings now is an easy win.",
                        "numbers": {"spent": s["month_spent"], "budget": s["total_budget"], "projected": round(projected, 2)},
                        "action": None})
        for cat, lim in s["category_budgets"].items():
            spent = s["by_category"].get(cat, 0)
            if lim and spent > lim:
                out.append({"id": f"cat-{cat}", "kind": "budget", "priority": "tip",
                            "title": f"{cat.title()} is over its limit",
                            "body": f"{money(spent)} spent of {money(lim)}. Two fewer {cat} outings this week would bring it back.",
                            "numbers": {"spent": spent, "limit": lim}, "action": None})
    bills = s["bills_before_payday"]
    if bills:
        total = sum(b["amount"] for b in bills)
        bal = s["available_balance"]
        ok = bal is None or bal >= total
        nxt = bills[0]
        out.append({"id": "bills", "kind": "bills", "priority": "money" if not ok else "tip",
                    "title": f"{len(bills)} bill{'s' if len(bills) > 1 else ''} before payday · {money(total)}",
                    "body": (f"Next: {nxt['title']} ({money(nxt['amount'])}) on {datetime.fromisoformat(nxt['due']):%d %b}. "
                             + ("Your balance covers them." if ok and bal is not None else
                                f"Your balance ({money(bal)}) is {money(total - bal)} short — move money in before then." if not ok else "")),
                        "numbers": {"bills": [{"title": b["title"], "amount": b["amount"], "due": b["due"]} for b in bills]},
                        "action": None})
    return out


def _renewals(db: Session, user_id: str, now: datetime) -> list[dict]:
    out = []
    for sub in budget_agent.detect_subscriptions(db, user_id):
        nxt = datetime.fromisoformat(sub["next_expected"]).replace(tzinfo=UTC)
        d = (nxt - now).days
        if -1 <= d <= 5:
            out.append({"id": f"sub-{sub['payee']}", "kind": "renewal", "priority": "tip",
                        "title": f"{sub['payee']} renews {'today' if d <= 0 else 'in ' + fdays(d)}",
                        "body": f"{money(sub['amount'])} every ~{sub['every_days']} days — about {money(sub['amount'] * 12 * 30 / max(sub['every_days'], 1) / 12 * 12)} a year.",
                        "numbers": {"amount": sub["amount"]}, "action": None})
    return out


def _business(db: Session, user_id: str, now: datetime) -> list[dict]:
    out = []
    obs = db.scalars(select(Obligation).where(Obligation.owner_id == user_id, Obligation.status == "open",
                                              Obligation.kind.in_(budget_agent.BUSINESS_KINDS))).all()
    for o in sorted(obs, key=lambda o: o.due_at):
        t = temporal(o.due_at, now)
        if t["status"] == "expired" or t["days_left"] > 14:
            continue
        out.append({"id": f"sup-{o.id}", "kind": "supplier", "priority": "urgent" if t["days_left"] <= 2 else "money",
                    "title": f"{o.title.split(' — ')[0]} is due {'tomorrow' if t['days_left'] < 1.5 else 'in ' + fdays(t['days_left'])}",
                    "body": f"{money(o.amount)} for {o.title.split(' — ')[-1]}. ContextIQ will check it against the purchase order before you pay.",
                    "numbers": {"days_left": max(0, round(t["days_left"])), "window_days": 14, "amount": o.amount},
                    "action": {"label": "Review and pay", "go": "pay"}})
    s = budget_agent.status(db, user_id, now, purpose="business")
    if s["month_spent"]:
        top = next(iter(s["by_category"].items()), None)
        out.append({"id": "biz-month", "kind": "budget", "priority": "good",
                    "title": f"Business spend this month: {money(s['month_spent'])}",
                    "body": (f"Biggest line: {top[0]} at {money(top[1])}. " if top else "") +
                            "Kept separate from your personal budget automatically.",
                    "numbers": {"spent": s["month_spent"]}, "action": None})
    return out


def _today(db: Session, user_id: str, now: datetime, ctx) -> list[dict]:
    """Time-of-day cards: what's due today in the morning, what you spent today in the evening."""
    out = []
    if ctx.part == "morning":
        due = db.scalars(select(Obligation).where(Obligation.owner_id == user_id, Obligation.status == "open",
                                                  Obligation.due_at <= now + timedelta(days=1, hours=12))).all()
        due = [o for o in due if (o.kind in budget_agent.BUSINESS_KINDS) == (ctx.account == "business") and o.amount > 0]
        if due:
            out.append({"id": "today", "kind": "today", "priority": "urgent",
                        "title": f"Due by tomorrow: {money(sum(o.amount for o in due))}",
                        "body": ", ".join(f"{o.title} ({money(o.amount)})" for o in due) + ".",
                        "numbers": {}, "action": None})
    elif ctx.part in ("evening", "night"):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0,
                                                    LedgerEntry.purpose == ctx.account)).all()
        spent = sum(r.amount for r in rows if _aware(r.occurred_at) >= start)
        if ctx.account == "business":
            return out  # business money is covered by the month card; no "today" nudge
        out.append({"id": "today", "kind": "today", "priority": "good",
                    "title": f"Today you spent {money(spent)}" if spent else "No spending today",
                    "body": "Nice — a zero-spend day helps the month more than you'd think." if not spent
                    else "Counted in your monthly pace.", "numbers": {"spent": spent}, "action": None})
    return out


def _payday(db: Session, user: User, now: datetime) -> list[dict]:
    s = budget_agent.status(db, user.id, now)
    d = (datetime.fromisoformat(s["next_payday"]).replace(tzinfo=UTC) - now).days
    if 0 <= d <= 2 and user.monthly_income:
        save = round(user.monthly_income * 0.1, -1)
        return [{"id": "payday", "kind": "save", "priority": "tip",
                 "title": "Payday " + ("tomorrow" if d <= 1 else f"in {d} days"),
                 "body": f"Move {money(save)} (10%) to savings the moment it lands — before it gets spent.",
                 "numbers": {"amount": save}, "action": None}]
    return []


GOAL_KINDS = {"save": {"save", "budget"}, "overspend": {"budget", "today"}, "deadlines": {"deadline", "bills", "supplier", "today"},
              "deals": {"price_drop"}}


def generate(db: Session, user_id: str, now: datetime | None = None, ctx=None) -> dict:
    from .context import decide

    now = now or datetime.now(UTC)
    user = db.get(User, user_id)
    if ctx is None:
        local = now + timedelta(hours=5, minutes=30)
        ctx = decide(user, local.hour, local.weekday())
    if ctx.account == "business":
        cards = _today(db, user_id, now, ctx) + _business(db, user_id, now)
    else:
        cards = (_today(db, user_id, now, ctx) + _deadlines(db, user_id, now) + _price_drops(db, user_id, now)
                 + _budget(db, user_id, now) + _renewals(db, user_id, now) + _payday(db, user, now))
    if ctx.travel:
        cards.insert(0, {"id": "travel", "kind": "travel", "priority": "tip", "title": "Travel mode is on",
                         "body": f"You're about {round(ctx.km_from_home)} km from home. Payments here won't be flagged "
                                 "just for the location, and you'll get a heads-up on card fees.", "numbers": {}, "action": None})
    goals = set(filter(None, (user.goals or "").split(",")))
    boosted = set().union(*(GOAL_KINDS.get(g, set()) for g in goals)) if goals else set()
    cards.sort(key=lambda c: (PRIORITY[c["priority"]], 0 if c["kind"] in boosted else 1))
    s = budget_agent.status(db, user_id, now, purpose=ctx.account)
    avail = user.available_balance if user and user.available_balance is not None else s.get("available_balance")
    bills_tot = s.get("bills_total", round(sum(b["amount"] for b in s.get("bills_before_payday", [])), 2))
    free_c = round((avail or 0.0) - bills_tot, 2) if avail is not None else None
    return {"greeting": _greet(ctx.part, user.name.split()[0] if user else ""), "context": ctx.as_dict(), "cards": cards,
            "summary": {"spent": s["month_spent"], "budget": s["total_budget"] if ctx.account == "personal" else None,
                        "remaining": s["remaining"] if ctx.account == "personal" else None,
                        "by_category": s["by_category"], "next_payday": s["next_payday"],
                        "balance": avail, "bills_total": bills_tot, "free_cash": free_c,
                        "monthly_income": user.monthly_income if user else None, "pay_day": user.pay_day if user else None}}


def _greet(part: str, name: str) -> str:
    return f"Good {'evening' if part == 'night' else part}, {name}"


def watch_cart(db: Session, user_id: str, merchant: str, items: list[dict], currency: str, url: str = "") -> None:
    from .agents.commerce import _product_key

    for it in items:
        key = _product_key(merchant, it["name"])
        if not db.scalar(select(CartItem).where(CartItem.user_id == user_id, CartItem.product_key == key)):
            db.add(CartItem(user_id=user_id, merchant=merchant, name=it["name"], product_key=key, currency=currency, url=url))


def spending_trend(db: Session, user_id: str, days: int = 30) -> list[dict]:
    now = datetime.now(UTC)
    start = now - timedelta(days=days - 1)
    rows = db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id, LedgerEntry.amount > 0)).all()
    by_day = {(start + timedelta(days=i)).date().isoformat(): 0.0 for i in range(days)}
    for r in rows:
        d = _aware(r.occurred_at).date().isoformat()
        if d in by_day:
            by_day[d] += r.amount
    return [{"date": d, "spent": round(v, 2)} for d, v in by_day.items()]
