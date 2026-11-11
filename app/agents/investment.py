"""Investment intelligence expert (optional, user-activated, education only).

What it does: checks liquidity first (can this money be invested without hurting upcoming
obligations?), explains options by risk level, and runs simple scenario ranges.
What it does NOT do: recommend specific securities or predict winners. Personalised investment
advice is regulated (e.g. SEBI Investment Adviser rules in India); this expert stays general.
Market data: no provider is connected in this build, so it never quotes live prices.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..fmt import money
from ..models import User
from . import budget as budget_agent

DISCLAIMER = ("General education, not investment advice. ContextIQ doesn't recommend specific securities; "
              "for personal advice consult a registered adviser.")

# illustrative long-run annual return / volatility assumptions per bucket (not forecasts)
BUCKETS = {
    "emergency_fund": {"label": "Savings / emergency fund", "mu": 0.035, "sigma": 0.005},
    "short_term_debt": {"label": "Short-term deposits or debt funds", "mu": 0.06, "sigma": 0.02},
    "balanced": {"label": "Balanced / hybrid funds", "mu": 0.08, "sigma": 0.09},
    "broad_equity_index": {"label": "Broad equity index funds", "mu": 0.10, "sigma": 0.17},
}


def scenarios(amount: float, years: float, bucket: str, n: int = 4000, seed: int = 0) -> dict:
    b = BUCKETS[bucket]
    rng = np.random.default_rng(seed)
    r = rng.normal(b["mu"] * years, b["sigma"] * np.sqrt(years), n)
    vals = amount * np.exp(r)
    return {"bucket": b["label"], "years": years, "p10": round(float(np.quantile(vals, 0.1)), 2),
            "median": round(float(np.median(vals)), 2), "p90": round(float(np.quantile(vals, 0.9)), 2),
            "chance_of_loss": round(float((vals < amount).mean()), 3)}


def advise(db: Session, user_id: str, amount: float, horizon_months: int = 1) -> dict:
    user = db.get(User, user_id)
    if not user or not user.investment_enabled:
        return {"enabled": False, "message": "Investment intelligence is off. Turn it on in settings to use it.",
                "disclaimer": DISCLAIMER}
    s = budget_agent.status(db, user_id)
    bills = sum(b["amount"] for b in s["bills_before_payday"])
    balance = s["available_balance"]
    if balance is None:
        liquidity = {"status": "unknown", "message": "I don't know your balance — enter it so I can check "
                     "whether this money is needed for upcoming bills."}
        investable = None
    else:
        reserve = bills + 0.25 * (user.monthly_income or 0)  # bills + about a week of income as buffer
        investable = max(0.0, round(balance - reserve, 2))
        if amount > investable:
            liquidity = {"status": "needed_soon",
                         "message": f"Of the {money(amount)}, only about {money(investable)} is truly spare once you "
                                    f"cover {money(bills)} of bills before payday and keep a small safety cushion. "
                                    "I'd keep the rest easy to reach for now."}
        else:
            liquidity = {"status": "ok", "message": f"{money(amount)} isn't needed for your bills before payday, so "
                                                    "it could be put aside for longer."}
    years = max(horizon_months / 12, 1 / 12)
    buckets = ["emergency_fund", "short_term_debt"] if horizon_months < 12 else \
        ["short_term_debt", "balanced"] + (["broad_equity_index"] if user.risk_tolerance != "low" else [])
    if horizon_months >= 60 and user.risk_tolerance == "high":
        buckets = ["balanced", "broad_equity_index"]
    sims = [scenarios(min(amount, investable) if investable is not None else amount, max(years, 1.0), b) for b in buckets]
    return {"enabled": True, "liquidity": liquidity, "investable": investable, "horizon_months": horizon_months,
            "risk_tolerance": user.risk_tolerance, "options": sims,
            "principles": ["Keep 3–6 months of expenses liquid before investing.",
                           "Money needed within a year belongs in low-volatility options.",
                           "Diversified index funds spread single-company risk.",
                           "No one can reliably predict which company will win."],
            "market_data": "not connected in this build", "disclaimer": DISCLAIMER}
