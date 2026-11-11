"""SENTRA-inspired security monitoring + isolated deception responder.

- ingest(): security telemetry with an integrity hash chain (tamper-evident log)
- correlate(): groups recent events per user/session into incidents
- decoy_response(): for sessions the gateway has *blocked*, returns generic synthetic data.
  It has NO database or PayPal access by construction — it only reads constants here —
  so it can never leak real data or move money.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SecurityEvent

_last_hash = "0" * 64


def ingest(db: Session, *, kind: str, user_id: str | None = None, session_id: str | None = None,
           severity: str = "info", detail: dict | None = None) -> SecurityEvent:
    global _last_hash
    detail = dict(detail or {})
    chained = hashlib.sha256((_last_hash + json.dumps([kind, user_id, session_id, detail], sort_keys=True,
                                                         default=str)).encode()).hexdigest()
    detail["chain_hash"] = chained
    _last_hash = chained
    ev = SecurityEvent(kind=kind, user_id=user_id, session_id=session_id, severity=severity, detail=detail)
    db.add(ev)
    db.flush()
    return ev


def correlate(db: Session, window_minutes: int = 60) -> list[dict]:
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    events = db.scalars(select(SecurityEvent)).all()
    groups: dict[str, list[SecurityEvent]] = defaultdict(list)
    for e in events:
        ts = e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=UTC)
        if ts >= since:
            groups[e.user_id or e.session_id or "unknown"].append(e)
    incidents = []
    for who, evs in groups.items():
        score = sum({"info": 0, "warning": 1, "critical": 3}.get(e.severity, 0) for e in evs)
        if score >= 2:
            incidents.append({"subject": who, "events": len(evs), "score": score,
                              "kinds": sorted({e.kind for e in evs}),
                              "severity": "critical" if score >= 5 else "warning"})
    return sorted(incidents, key=lambda i: -i["score"])


_DECOY = {
    "balance": {"currency": "USD", "value": "0.00"},
    "cases": [],
    "message": "Service temporarily unavailable. Please try again later.",
}


def decoy_response(kind: str) -> dict:
    """Isolated: pure function over constants. No db/session/client parameters exist here."""
    return {kind: _DECOY[kind]} if kind in _DECOY else {"message": _DECOY["message"]}
