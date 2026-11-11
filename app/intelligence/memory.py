"""Four memory categories, retrieved least-privilege per expert.

Each expert declares which memory kinds it may read. Retrieval returns the smallest relevant set:
items are filtered by permission first, then ranked by text relevance × recency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

_vec = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 4), n_features=2**14, alternate_sign=False, norm="l2")

MEMORY_KINDS = ("context", "personal", "briefcase", "financial")

# which memory each expert may read (seller-side experts never see buyer financial memory)
EXPERT_SCOPE = {
    "payment": {"context", "briefcase"},
    "refund": {"context", "briefcase"},
    "policy": {"context", "briefcase"},
    "cart": {"context", "personal", "briefcase"},
    "helpdesk": {"context", "briefcase", "personal"},
    "invoice": {"context", "briefcase"},
    "budget": {"context", "briefcase", "financial", "personal"},
    "fraud": {"context", "briefcase"},
    "coordination": {"briefcase"},
    "subscription": {"briefcase", "financial"},
    "investment": {"financial", "personal"},
    "price": {"personal", "briefcase"},
}


@dataclass
class MemoryItem:
    kind: str
    text: str
    ref: str
    at: datetime
    owner: str
    data: dict = field(default_factory=dict)


def retrieve(items: list[MemoryItem], *, expert: str, query: str, requester: str, k: int = 6,
             half_life_days: float = 30) -> list[MemoryItem]:
    allowed = EXPERT_SCOPE.get(expert, {"context"})
    pool = [m for m in items if m.kind in allowed and m.owner == requester]
    if not pool:
        return []
    q = _vec.transform([query])
    M = _vec.transform([m.text for m in pool])
    sim = (M @ q.T).toarray().ravel()
    now = datetime.now(UTC)
    rec = np.array([math.exp(-max(0.0, (now - (m.at if m.at.tzinfo else m.at.replace(tzinfo=UTC)))
                                   .total_seconds() / 86400) / half_life_days) for m in pool])
    score = 0.75 * sim + 0.25 * rec
    order = np.argsort(-score)[:k]
    return [pool[i] for i in order if score[i] > 0.05]
