"""Temporal knowledge graph over the briefcase.

Facts are (subject, predicate, object) edges with a time window [valid_from, valid_to) and a provenance
(verified / claimed / inferred). Built on demand from the authoritative tables, so it can never drift
from them. Supports:
  - as_of(t):          the graph as it stood at time t (what did we know, and when)
  - neighborhood():    multi-hop retrieval from an entity, permission-scoped to one party
  - retrieve():        graph + text retrieval (GraphRAG-style): text match picks seed nodes, the graph
                       expands to connected facts, the expert receives a small, relevant context pack
  - contradictions():  same subject+predicate, different values, overlapping time — e.g. PayPal says paid,
                       seller claims not paid
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agreement, Case, CaseEvent, Evidence, Obligation, Participant, User

_vec = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 4), n_features=2**14, alternate_sign=False, norm="l2")
FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass
class Fact:
    s: str
    p: str
    o: str
    valid_from: datetime
    valid_to: datetime = FAR_FUTURE
    provenance: str = "verified"
    source: str = ""
    case_id: str | None = None


@dataclass
class TKG:
    facts: list[Fact] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    owner: dict[str, set] = field(default_factory=lambda: defaultdict(set))  # node -> parties allowed to see it

    def add(self, f: Fact, visible_to: set[str]):
        self.facts.append(f)
        for n in (f.s, f.o):
            self.owner[n] |= visible_to

    def as_of(self, t: datetime) -> list[Fact]:
        return [f for f in self.facts if f.valid_from <= t < f.valid_to]

    def neighborhood(self, start: str, party: str, hops: int = 2, t: datetime | None = None) -> list[Fact]:
        facts = self.as_of(t) if t else self.facts
        adj = defaultdict(list)
        for f in facts:
            if party in self.owner[f.s] and party in self.owner[f.o]:
                adj[f.s].append(f)
                adj[f.o].append(f)
        seen, out, q = {start}, [], deque([(start, 0)])
        while q:
            n, d = q.popleft()
            if d == hops:
                continue
            for f in adj[n]:
                if f not in out:
                    out.append(f)
                for m in (f.s, f.o):
                    if m not in seen:
                        seen.add(m)
                        q.append((m, d + 1))
        return out

    def retrieve(self, query: str, party: str, k_seeds: int = 3, hops: int = 2) -> dict:
        nodes = [n for n in self.labels if party in self.owner[n]]
        if not nodes:
            return {"seeds": [], "facts": []}
        M = _vec.transform([self.labels[n] for n in nodes])
        sims = (M @ _vec.transform([query]).T).toarray().ravel()
        seeds = [nodes[i] for i in np.argsort(-sims)[:k_seeds] if sims[i] > 0.05]
        facts: list[Fact] = []
        for sd in seeds:
            for f in self.neighborhood(sd, party, hops):
                if f not in facts:
                    facts.append(f)
        return {"seeds": [{"id": s, "label": self.labels[s]} for s in seeds],
                "facts": [self.render(f) for f in facts[:25]]}

    def contradictions(self) -> list[dict]:
        groups = defaultdict(list)
        for f in self.facts:
            groups[(f.s, f.p)].append(f)
        out = []
        for (s, p), fs in groups.items():
            vals = {f.o for f in fs}
            if len(vals) < 2:
                continue
            for a in fs:
                for b in fs:
                    if a.o < b.o and a.valid_from < b.valid_to and b.valid_from < a.valid_to:
                        winner = a if _rank(a) >= _rank(b) else b
                        out.append({"subject": self.labels.get(s, s), "about": p, "values": [a.o, b.o],
                                    "sources": [f"{a.provenance} ({a.source})", f"{b.provenance} ({b.source})"],
                                    "trust": f"{winner.o} — {winner.provenance} evidence outranks the other"})
        return out

    def render(self, f: Fact) -> dict:
        return {"subject": self.labels.get(f.s, f.s), "relation": f.p.replace("_", " "), "object": self.labels.get(f.o, f.o),
                "from": f.valid_from.isoformat()[:16], "to": None if f.valid_to == FAR_FUTURE else f.valid_to.isoformat()[:16],
                "provenance": f.provenance}


def _rank(f: Fact) -> int:
    return {"verified": 3, "claimed": 2, "inferred": 1}.get(f.provenance, 0)


PAYMENT_STATE_EVENTS = {"payment_order_created": "order created", "payment_buyer_approved": "approved",
                        "payment_capture_pending": "pending", "payment_captured": "paid",
                        "payment_partially_refunded": "partially refunded", "payment_refunded": "refunded",
                        "payment_failed": "failed"}


def build(db: Session) -> TKG:
    g = TKG()
    for u in db.scalars(select(User)).all():
        g.labels[f"party:{u.id}"] = f"{u.business_name or u.name} ({u.role})"
    for c in db.scalars(select(Case)).all():
        cid, created = f"case:{c.id}", _aware(c.created_at)
        parts = {p.party_id: p.role for p in db.scalars(select(Participant).where(Participant.case_id == c.id)).all()}
        vis = set(parts)
        g.labels[cid] = f"{c.title} {c.merchant} {c.category} {c.purpose} purchase"
        buyer = next((p for p, r in parts.items() if r == "buyer"), c.owner_id)
        g.add(Fact(f"party:{buyer}", "bought", cid, created, case_id=c.id), vis)
        seller = next((p for p, r in parts.items() if r == "seller"), None)
        mid = f"party:{seller}" if seller else f"merchant:{c.merchant}"
        g.labels.setdefault(mid, f"{c.merchant} seller supplier merchant")
        g.add(Fact(cid, "sold_by", mid, created, case_id=c.id), vis)
        ag = db.scalar(select(Agreement).where(Agreement.case_id == c.id))
        if ag:
            for it in ag.items:
                pid = f"product:{it['name'].lower()}"
                g.labels[pid] = it["name"]
                g.add(Fact(cid, "contains", pid, created, case_id=c.id), vis)
            g.add(Fact(cid, "agreed_amount", f"{ag.amount:.2f} {ag.currency}", created, source="signed agreement",
                       case_id=c.id), vis)
        # payment status as a time-sliced property: each state is valid until the next one
        evs = db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.occurred_at)).all()
        states = [(_aware(e.occurred_at), PAYMENT_STATE_EVENTS[e.type], e.source) for e in evs if e.type in PAYMENT_STATE_EVENTS]
        for i, (t, st, src) in enumerate(states):
            nxt = states[i + 1][0] if i + 1 < len(states) else FAR_FUTURE
            g.add(Fact(cid, "payment_status", st, t, nxt, "verified", src, c.id), vis)
        for e in evs:
            if e.type == "delivered":
                g.add(Fact(cid, "delivered", "yes", _aware(e.occurred_at), provenance="verified" if e.source != "user" else "claimed",
                           source=e.source, case_id=c.id), vis)
        for ev in db.scalars(select(Evidence).where(Evidence.case_id == c.id, Evidence.kind.like("claim_%"))).all():
            topic = ev.content.get("topic")
            if not topic:  # e.g. "claim_draft" evidence is a refund draft, not a buyer/seller claim
                continue
            pred = {"paid": "payment_status", "delivered": "delivered"}.get(topic, topic)
            val = ("paid" if ev.content.get("value") else "not paid") if topic == "paid" else ("yes" if ev.content.get("value") else "no")
            g.add(Fact(cid, pred, val, _aware(ev.created_at), provenance="claimed", source=f"the {ev.content.get('role')}",
                       case_id=c.id), vis)
        for o in db.scalars(select(Obligation).where(Obligation.case_id == c.id)).all():
            oid = f"ob:{o.id}"
            g.labels[oid] = f"{o.kind.replace('_', ' ')} deadline {o.title}"
            g.add(Fact(cid, "has_deadline", oid, created, _aware(o.due_at) if o.status == "open" else created, case_id=c.id),
                  {c.owner_id})  # deadlines are the buyer's own memory
    return g
