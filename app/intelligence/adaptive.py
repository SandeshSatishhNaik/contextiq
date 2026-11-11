"""Vertical adaptive layer (RL): Thompson-sampling contextual bandit.

Learns, per user and context, which *permitted* presentation choice works best — shortcut order,
reminder timing — from consented feedback (tapped / dismissed). It never changes what actions
are allowed; it only reorders and times them. Feedback is clipped per event so one burst of
fake feedback cannot swing it (basic poisoning resistance).
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BanditArm

SHORTCUTS = ["quick_checkout", "refund_tracker", "active_purchases", "budget", "bills_reminders",
             "price_watch", "merchant_qr", "invoices", "investments"]
REMINDER_TIMES = ["morning", "lunch", "evening", "two_days_before", "day_before"]


def _arm(db: Session, user_id: str, context: str, arm: str) -> BanditArm:
    a = db.scalar(select(BanditArm).where(BanditArm.user_id == user_id, BanditArm.context == context,
                                          BanditArm.arm == arm))
    if not a:
        a = BanditArm(user_id=user_id, context=context, arm=arm, alpha=1.0, beta=1.0)
        db.add(a)
        db.flush()
    return a


def rank(db: Session, user_id: str, context: str, arms: list[str], boosts: dict[str, float] | None = None,
         seed: int | None = None) -> list[str]:
    rng = np.random.default_rng(seed)
    boosts = boosts or {}
    draws = {}
    for arm in arms:
        a = _arm(db, user_id, context, arm)
        draws[arm] = rng.beta(a.alpha, a.beta) + boosts.get(arm, 0.0)
    return sorted(arms, key=lambda k: -draws[k])


def feedback(db: Session, user_id: str, context: str, arm: str, reward: float) -> None:
    reward = float(np.clip(reward, 0.0, 1.0))
    a = _arm(db, user_id, context, arm)
    a.alpha += reward
    a.beta += 1.0 - reward
    # cap total evidence so the model keeps adapting to changing routines
    total = a.alpha + a.beta
    if total > 200:
        a.alpha, a.beta = a.alpha * 200 / total, a.beta * 200 / total


def simulate_learning(true_rates: dict[str, float], rounds: int = 300, seed: int = 0) -> dict:
    """Offline check on simulated feedback: does the bandit find the best arm?"""
    rng = np.random.default_rng(seed)
    ab = {k: [1.0, 1.0] for k in true_rates}
    picks = []
    for _ in range(rounds):
        k = max(ab, key=lambda a: rng.beta(*ab[a]))
        r = float(rng.random() < true_rates[k])
        ab[k][0] += r
        ab[k][1] += 1 - r
        picks.append(k)
    best = max(true_rates, key=true_rates.get)
    return {"best_arm": best, "share_of_last_100_on_best": picks[-100:].count(best) / 100}
