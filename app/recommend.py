"""Recommendation engine: turns budget pace + cart + investing + bills into a few concrete plans.

Candidates are built from real numbers (deterministic). Their order is learned per user by the
Thompson-sampling bandit (intelligence/adaptive.py): "Do it" = reward 1, "Not for me" = reward 0.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import insights as ins
from .agents import budget as budget_agent
from .agents import investment
from .fmt import money
from .intelligence import adaptive
from .models import CartItem, PriceObservation, User

FLEX = ("dining", "clothing", "entertainment", "shopping", "transport")


def _cart(db: Session, uid: str) -> list[dict]:
    out = []
    for it in db.scalars(select(CartItem).where(CartItem.user_id == uid, CartItem.active.is_(True))).all():
        h = [p.price for p in db.scalars(select(PriceObservation).where(PriceObservation.product_key == it.product_key)
                                         .order_by(PriceObservation.seen_at)).all()]
        if h:
            out.append({"id": it.id, "name": it.name, "now": h[-1], "first": h[0], "low": min(h), "high": max(h[:-1] or h)})
    return out


def build(db: Session, uid: str) -> dict:
    now = datetime.now(UTC)
    user = db.get(User, uid)
    pc = ins._pace(db, uid, now)
    budget = pc["status"]["total_budget"] or 0
    spare = round(budget - pc["projected"], 2) if budget else 0.0
    weeks = max(1.0, pc["days_left"] / 7)
    weekly = {k: v / pc["elapsed"] * 7 for k, v in pc["per_cat"].items() if k in FLEX}
    cart = _cart(db, uid)
    dropped = [c for c in cart if c["now"] < c["high"]]
    rose = [c for c in cart if c["now"] > c["first"]]
    adv = investment.advise(db, uid, max(spare, 0) * 0.5, 12) if user and user.investment_enabled else {"enabled": False}
    invest_amt = 0.0
    if adv.get("enabled") and adv.get("investable"):
        invest_amt = max(0.0, round(min(adv["investable"], max(spare, 0) * 0.5, 500) / 10) * 10)
    cands: dict[str, dict] = {}

    # 1) the combined plan: buy what dropped + put money aside, and what to trim to afford both
    if dropped or invest_amt:
        buy = dropped[0] if dropped else None
        need = (buy["now"] if buy else 0) + invest_amt
        gap = round(need - max(spare, 0), 2)
        what = " and ".join(x for x in [f"buy the {buy['name']} ({money(buy['now'])})" if buy else "",
                                        f"put {money(invest_amt)} into savings" if invest_amt else ""] if x)
        cuts = []
        if gap > 0 and weekly:
            total_w = sum(weekly.values())
            for k, w in sorted(weekly.items(), key=lambda x: -x[1]):
                c = min(w * 0.4, gap / weeks * w / total_w)
                if c >= 3:
                    cuts.append((k, round(c)))
        if gap <= 0:
            body = f"You can {what} and still finish the month about {money(-gap + 0)} under budget."
            steps = [f"Buy the {buy['name']} while it's {money(buy['now'])}" if buy else "",
                     f"Move {money(invest_amt)} to savings on payday" if invest_amt else ""]
        else:
            cut_txt = " and ".join(f"{k} by {money(v, dp=0)} a week" for k, v in cuts[:2]) or "non-essentials"
            body = (f"To {what}, you're {money(gap)} short this month at your current pace. "
                    f"Cutting {cut_txt} until payday covers it.")
            steps = [f"Spend about {money(v, dp=0)} less on {k} each week" for k, v in cuts[:2]] + \
                    ([f"Then buy the {buy['name']}" if buy else ""]) + ([f"Move {money(invest_amt)} to savings on payday"] if invest_amt else [])
        cands["plan"] = {"title": "Your plan for this month", "body": body, "steps": [s for s in steps if s],
                         "numbers": {"spare": spare, "need": need, "gap": max(gap, 0), "cuts": cuts}, "go": "budget"}
    # 2) wait on items whose price went up
    for c in rose[:1]:
        cands["wait_price"] = {"title": f"Hold off on the {c['name']}",
                               "body": f"It's {money(c['now'])} now but was {money(c['first'])} when you added it. "
                                       "Prices usually come back down — I'll tell you when it does.",
                               "steps": [], "numbers": {"history": [c["first"], c["now"]]}, "go": "cart"}
    # 3) subscriptions worth a look
    from .models import LedgerEntry

    biz = {e.payee for e in db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == uid, LedgerEntry.purpose == "business")).all()}
    subs = [x for x in budget_agent.detect_subscriptions(db, uid) if x["payee"] not in biz]
    if subs:
        s = max(subs, key=lambda x: x["amount"])
        yearly = s["amount"] * 365 / max(1, s["every_days"])
        cands["subs"] = {"title": f"{s['payee']} costs {money(yearly, dp=0)} a year",
                         "body": f"If you're not using it much, pausing it for a month frees {money(s['amount'])} — enough to cover part of your plan.",
                         "steps": [], "numbers": {}, "go": "budget"}
    # 4) payday habit
    if user and user.monthly_income:
        save = round(user.monthly_income * 0.1, -1)
        cands["payday_save"] = {"title": f"Pay yourself first: {money(save, dp=0)} on payday",
                                "body": f"Moving 10% of your pay to savings the day it lands builds {money(save * 12, dp=0)} a year without feeling it.",
                                "steps": [], "numbers": {}, "go": "invest"}
    # 5) biggest flexible category
    if weekly:
        k, w = max(weekly.items(), key=lambda x: x[1])
        cands["trim_top"] = {"title": f"{k.title()} is your biggest flexible spend",
                             "body": f"About {money(w, dp=0)} a week. Trimming a quarter saves {money(w * 0.25 * 4.3, dp=0)} a month.",
                             "steps": [], "numbers": {}, "go": "budget"}
    boosts = {"plan": 0.6, "wait_price": 0.2}
    order = adaptive.rank(db, uid, "recs", list(cands), boosts=boosts) if cands else []
    return {"items": [{"id": a} | cands[a] for a in order], "spare": spare, "invest_amount": invest_amt,
            "investable": adv.get("investable"), "weeks_left": round(weeks, 1)}
