"""Red-team attack generator — kept separate from synth.py on purpose.

Rule for the team: whoever edits this file should not edit synth.py or the model features,
so attack assumptions don't leak into the training data.

Families:
  TRAIN families   : account_takeover, amount_spike, payee_change
  HELD-OUT families: invoice_inflation, urgency_wording   (never seen in training)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .synth import urgency_score

TRAIN_FAMILIES = ["account_takeover", "amount_spike", "payee_change"]
HELDOUT_FAMILIES = ["invoice_inflation", "urgency_wording"]


def _base(rng, n):
    return {
        "amount_z": rng.normal(0.3, 1.0, n), "log_amount": rng.normal(4.2, 1.0, n),
        "new_payee": (rng.random(n) < 0.2).astype(int), "payee_changed_recently": np.zeros(n, int),
        "new_device": (rng.random(n) < 0.1).astype(int), "ip_country_mismatch": (rng.random(n) < 0.05).astype(int),
        "unusual_hour": (rng.random(n) < 0.15).astype(int), "burst_1h": rng.poisson(0.6, n),
        "invoice_po_ratio": np.ones(n), "urgency_score": np.zeros(n), "session_age_min": rng.exponential(30, n),
    }


def attacks(family: str, n: int, seed: int = 99, stealth: float = 0.0) -> pd.DataFrame:
    """stealth in [0, 1): attackers who hide better (fewer red flags). Used only for unseen evaluation."""
    rng = np.random.default_rng(seed + sum(map(ord, family)))  # stable across runs
    d = _base(rng, n)
    if family == "account_takeover":
        d["new_device"] = (rng.random(n) < 0.85).astype(int)
        d["ip_country_mismatch"] = (rng.random(n) < 0.7).astype(int)
        d["unusual_hour"] = (rng.random(n) < 0.6).astype(int)
        d["new_payee"] = (rng.random(n) < 0.8).astype(int)
        d["session_age_min"] = rng.exponential(3, n)
        d["amount_z"] = rng.normal(2.0, 1.2, n)
        d["burst_1h"] = rng.poisson(2.5, n)
    elif family == "amount_spike":
        d["amount_z"] = rng.uniform(4, 15, n)
        d["log_amount"] = rng.normal(6.5, 0.8, n)
    elif family == "payee_change":
        # no urgency wording here: keeps the urgency family genuinely unseen in training
        d["payee_changed_recently"] = (rng.random(n) < 0.9).astype(int)
        d["amount_z"] = rng.normal(1.0, 1.0, n)
    elif family == "invoice_inflation":
        # subtle: familiar payee, normal device, only the invoice exceeds the agreed PO
        d["invoice_po_ratio"] = rng.uniform(1.06, 1.6, n)
        d["new_payee"] = np.zeros(n, int)
        d["amount_z"] = rng.normal(0.8, 0.8, n)
    elif family == "urgency_wording":
        texts = rng.choice(["URGENT: final notice, wire now to avoid penalty",
                            "account suspended - act now, new bank details attached",
                            "confidential: pay immediately, today only"], n)
        d["urgency_score"] = np.array([urgency_score(t) for t in texts])
        d["new_payee"] = (rng.random(n) < 0.7).astype(int)
    else:
        raise ValueError(family)
    df = pd.DataFrame(d)
    if stealth:
        keep = rng.random(n) >= stealth  # each binary red flag disappears with probability `stealth`
        for col in ("new_device", "ip_country_mismatch", "unusual_hour", "new_payee"):
            df[col] = df[col] * (rng.random(n) >= stealth)
        df["amount_z"] = df["amount_z"] * np.where(keep, 1.0, 0.6)
        df["session_age_min"] = df["session_age_min"] * np.where(keep, 1.0, 5.0)
    df["family"] = family
    df["label"] = 1
    return df
