"""Versioned cache with metrics. Keys embed a content hash or case rev, so a change in the
underlying data can never serve a stale result. Payment state is never cached."""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

FORBIDDEN_PREFIXES = ("payment_state", "capture", "authorization", "risk_decision")


class Cache:
    def __init__(self, max_items: int = 2000):
        self._d: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._lock = Lock()
        self.max_items = max_items
        self.enabled = True
        self.hits = self.misses = 0
        self.tokens_saved = 0

    def get(self, key: str):
        if not self.enabled:
            self.misses += 1
            return None
        with self._lock:
            item = self._d.get(key)
            if item and (item[0] == 0 or item[0] > time.time()):
                self._d.move_to_end(key)
                self.hits += 1
                return item[1]
            self.misses += 1
            return None

    def set(self, key: str, value, ttl: float = 0) -> None:
        if key.startswith(FORBIDDEN_PREFIXES):
            raise ValueError(f"refusing to cache authoritative financial state: {key}")
        with self._lock:
            self._d[key] = (time.time() + ttl if ttl else 0, value)
            self._d.move_to_end(key)
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"enabled": self.enabled, "hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0, "tokens_saved": self.tokens_saved}


cache = Cache()
