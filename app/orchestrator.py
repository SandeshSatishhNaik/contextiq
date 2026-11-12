"""Central orchestrator (LangGraph).

understand → plan → experts → reason → decide → approval gate → respond

- understand: keyword rules first (exact, free), trained router second, GenAI third (if configured),
               otherwise ask the user a short "did you mean" question.
- plan:        picks the experts this request needs (often more than one).
- experts:     each returns a structured Finding (summary, data, confidence, unknowns, options, actions).
               Experts run one after another on one DB session, so results are deterministic.
- reason:      unified layer — merges uncertainty, flags contradictions between experts.
- decide:      ContextIQ decision model ranks permitted options when an expert offers choices.
- gate:        anything that would move money or contact someone becomes a proposal needing approval.
- respond:     plain-language answer; GenAI may smooth the wording but cannot change facts.
"""
from __future__ import annotations

import operator
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Send
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents import budget as budget_agent
from .agents import commerce, helpdesk, investment
from .agents import context as ctx_agent
from .agents import policy as policy_agent
from .fmt import money, nice
from .intelligence import llm
from .ml import runtime
from .models import Case, PolicySnapshot, PriceObservation

ROUTER_CONFIDENCE = 0.25  # chosen on held-out phrasings (see MODEL_REPORT.md)

RULES: list[tuple[str, str]] = [
    (r"\b(supplier|vendor|seller)\b.*\b(not|never|didn'?t|hasn'?t|wasn'?t|isn'?t)\b.*\b(receiv|paid|get)", "payment_status"),
    (r"\b(charged twice|double charge|did (my|the) payment|payment (go|went) through|is .* paid|payment status|crash(ed)? while pay|payment (is )?stuck|still pending|pending capture)\b", "payment_status"),
    (r"\b(return|refund|money back|replace(ment)?|swap|exchange|stopped working|broken|damaged|defect|faulty)", "refund"),
    (r"\b(invoice|purchase order|\bpo\b)", "invoice"),
    (r"\b(scam|suspicious|fraud|phishing|bank details|wire now|logged in from)", "fraud"),
    (r"\b(subscription|recurring|renew|auto-?pay)", "subscription"),
    (r"\b(invest|stocks?|shares|mutual fund|index fund|portfolio|diversif)", "investment"),
    (r"\b(price (drop|history)|cheaper|lowest price|good price|on sale|discount)", "price"),
    (r"\b(afford|budget|overspend|bills?|spending|spent|cash ?flow|rent|payday)", "budget"),
    (r"\b(policy|warranty|terms)", "policy"),
    (r"\b(my (purchases|orders|transactions)|briefcase|what('?s| is) (still )?open|show .* orders?|receipts?|history)", "cases"),
]

PLAN = {
    "refund": ["evidence", "policy", "refund"],
    "payment_status": ["evidence", "payment", "dispute"],
    "policy": ["evidence", "policy"],
    "budget": ["budget", "obligations"],
    "invoice": ["invoice"],
    "fraud": ["fraud"],
    "subscription": ["subscription"],
    "investment": ["budget", "investment"],
    "price": ["evidence", "price", "budget"],
    "cases": ["evidence"],
}
INTENT_LABEL = {"refund": "returns and refunds", "payment_status": "a payment check", "policy": "store terms",
                "budget": "your budget", "invoice": "an invoice", "fraud": "a possible scam",
                "subscription": "recurring payments", "investment": "investing", "price": "prices", "cases": "your purchases"}


@dataclass
class Finding:
    expert: str
    summary: str
    confidence: float = 1.0
    unknowns: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    decision: dict | None = None
    proposed_action: dict | None = None
    primary: bool = False


class S(TypedDict, total=False):
    db: Any
    user_id: str
    message: str
    case_id: str | None
    intent: str
    confidence: float
    route_source: str
    alternatives: list[str]
    plan: list[str]
    case: Any
    findings: Annotated[list, operator.add]   # parallel experts append here
    rounds: int                                 # evidence-gathering rounds so far
    requested: list[str]                        # experts the reasoning layer asked to run again / newly
    reasoning: dict
    decision: dict | None
    resolutions: list[str]
    answer: str
    proposal: dict | None
    trace: list[str]


# ------------------------------------------------------------------ nodes
RULE_FALLBACK_BELOW = 0.30   # chosen on the development set: model first, rules only when the model is unsure
ASK_BELOW = 0.20
FRAUD_SAFETY_RE = re.compile(r"\b(never made|didn'?t authorize|did not authorize|not me|unauthorized|stolen|hacked|fake charge|without (my )?consent)\b", re.I)


# Out-of-scope requests: the router has no "other" topic, so a joke or a weather question was forced into the
# nearest money topic. Only explicit off-topic markers count: a generic "low confidence and no money word" test
# also turned away 8% of real customer questions ("is accidental damage covered"), which is worse.
OFF_TOPIC_RE = re.compile(r"\b(jokes?|poem|story|song|sing (me|a)|lyrics|weather|cricket|football|soccer|nba|match score|"
                          r"who won|recipe|translate|capital of|celebrity|president|movie to watch|"
                          r"recommend a (movie|book|show)|how are you|what('?s| is) your name|"
                          r"\d+\s*[-+*/x]\s*\d+\s*$)", re.I)
PAYMENT_WORDS_RE = re.compile(r"\b(price|refund|bill|invoice|payment|paypal|subscription|charge|order|purchase|budget)\b", re.I)


def off_topic(message: str, router_confidence: float = 0.0) -> bool:
    return bool(OFF_TOPIC_RE.search(message)) and not PAYMENT_WORDS_RE.search(message)


def understand(state: S) -> S:
    """Trained router first; keyword rules only when it is unsure; then GenAI; then ask the user."""
    msg = state["message"]
    # Critical security override: unauthorized activity must always route to fraud to protect victims
    if FRAUD_SAFETY_RE.search(msg):
        return {"intent": "fraud", "confidence": 1.0, "route_source": "security override (unauthorized phrasing)",
                "alternatives": ["cases", "refund"], "trace": ["understood as a possible scam (security override, confidence 1.00)"]}

    m = runtime._load("router")
    proba = m.predict_proba([msg])[0]
    order = proba.argsort()[::-1]
    intent, p = str(m.classes_[order[0]]), float(proba[order[0]])
    alts = [str(m.classes_[i]) for i in order[1:3]]
    src = "trained router"
    if p < RULE_FALLBACK_BELOW:
        rule = next((i for pat, i in RULES if re.search(pat, msg.lower())), None)
        if rule:
            intent, src = rule, "keyword rule (router unsure)"
        elif llm.available():
            out = llm.complete("Classify the user's request into exactly one label: " + ", ".join(PLAN) +
                               ". Reply with the label only.", msg, max_tokens=6)
            if out and out.strip().lower() in PLAN:
                intent, src = out.strip().lower(), "GenAI reasoning"
        if src == "trained router" and p < ASK_BELOW:
            src = "unsure"
    return {"intent": intent, "confidence": p, "route_source": src, "alternatives": alts,
            "trace": [f"understood as {INTENT_LABEL[intent]} ({src}, confidence {p:.2f})"]}


def plan(state: S) -> S:
    db: Session = state["db"]
    case = db.get(Case, state["case_id"]) if state.get("case_id") else None
    if case is None and state["intent"] == "payment_status" and re.search(r"supplier|vendor|invoice", state["message"], re.I):
        case = db.scalars(select(Case).where(Case.owner_id == state["user_id"], Case.purpose == "business")
                          .order_by(Case.updated_at.desc())).first()
    if case is None and "evidence" in PLAN[state["intent"]]:
        case = helpdesk.find_case(db, state["user_id"], state["message"])
    p = PLAN[state["intent"]]
    return {"plan": p, "case": case, "rounds": 0, "requested": p,
            "trace": state["trace"] + [f"experts (in parallel): {', '.join(p)}" + (f"; purchase: {case.title}" if case else "")]}


def fan_out(state: S) -> list[Send]:
    """One branch per expert. Each branch gets only what it needs, never the shared DB session."""
    cid = state["case"].id if state.get("case") else None
    return [Send("expert", {"expert": ex, "user_id": state["user_id"], "message": state["message"], "case_id": cid,
                            "intent": state["intent"], "round": state.get("rounds", 0)})
            for ex in state.get("requested") or []]


def _amount(msg: str) -> float | None:
    m = re.search(r"(?:\$|₹|€|£|usd|inr|rs\.?)\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?(?:dollars|rupees|usd|inr|bucks)", msg, re.I)
    return float((m.group(1) or m.group(2)).replace(",", "")) if m else None


def expert(branch: dict) -> dict:
    """Runs ONE expert in its own DB session (safe to run in parallel with the others)."""
    from .db import SessionLocal

    db = SessionLocal()
    try:
        case = db.get(Case, branch["case_id"]) if branch.get("case_id") else None
        f = _run_expert(branch["expert"], db, branch["user_id"], branch["message"], case, branch["intent"])
        db.commit()
    except Exception as exc:  # noqa: BLE001 — one failing expert must not sink the answer
        db.rollback()
        f = Finding(branch["expert"], "", 0.0, [f"{branch['expert']} failed: {type(exc).__name__}"])
    finally:
        db.close()
    if f is None:
        return {"findings": []}
    f.data = {"round": branch.get("round", 0)} | (f.data or {})
    return {"findings": [f]}


def _run_expert(ex: str, db: Session, uid: str, msg: str, case: Case | None, intent: str) -> Finding | None:
    if ex == "evidence":
        if not case:
            return Finding("evidence", "I couldn't tell which purchase you mean.", 0.0, ["which purchase"], primary=intent == "cases")
        if intent == "cases":
            cases = helpdesk.list_cases(db, uid)
            lines = [f"{c['title']} from {c['merchant']} — {money(c['amount'], c['currency'])}, {nice(c['payment_state'])}"
                     for c in cases[:5]]
            return Finding("evidence", f"You have {len(cases)} purchase record(s). Most recent: " + "; ".join(lines) + ".",
                           data={"cases": cases}, primary=True)
        return Finding("evidence", f"Found your purchase: {case.title} from {case.merchant} ({money(case.amount, case.currency)}).",
                       data=bc_summary(db, case))
    if ex == "policy":
        snap = db.scalar(select(PolicySnapshot).where(PolicySnapshot.case_id == case.id)) if case else None
        if not snap:
            return Finding("policy", "I don't have the store's terms for this purchase.", 0.3, ["store policy"],
                           primary=intent == "policy")
        lines = policy_agent.explain(snap.extracted)
        return Finding("policy", "The store's terms when you bought it: " + " ".join(lines), 0.8,
                       data={"terms": snap.extracted}, primary=intent == "policy")
    if ex == "refund":
        if not case:
            return Finding("refund", "Tell me which order it is and I'll check your options.", 0.0, ["which order"], primary=True)
        d = commerce.draft_claim(db, case, msg)
        el = d["eligibility"]
        return Finding("refund", el["reason"], el["uncertainty"]["confidence"], el["uncertainty"]["missing"],
                       data={"eligibility_basis": el["basis"], "case_id": case.id, "_options": el["options"]},
                       primary=True)
    if ex == "payment":
        if not case:
            return Finding("payment", "I couldn't find that payment.", 0.0, ["which payment"], primary=True)
        inv = commerce.payment_investigation(db, case, supplier_claim="payment not received (reported by the buyer)")
        verdict_text = {
            "paid": "PayPal confirms this payment went through",
            "refunded": "PayPal shows this payment was refunded",
            "pending": "PayPal is holding this payment for now",
            "approved_not_captured": "you approved it, but the payment was never completed",
            "not_paid": "no money left your account for this order",
            "not_started": "this payment hasn't been started",
            "paid_to_different_account": "the payment went through, but possibly to a different account",
        }.get(inv["verdict"], "I couldn't confirm the payment state")
        ref = f" (PayPal reference {inv['capture_id']})" if inv.get("capture_id") else ""
        return Finding("payment", f"{verdict_text}{ref}. {inv['next_step']}", inv["uncertainty"]["confidence"],
                       inv["uncertainty"]["missing"], data=inv, primary=True)
    if ex == "delivery":
        if not case:
            return None
        from .models import CaseEvent as CE

        ev = db.scalar(select(CE).where(CE.case_id == case.id, CE.type == "delivered"))
        if ev:
            return Finding("delivery", f"Delivery was recorded on {ev.payload.get('at', '')[:10]}.", 1.0)
        return Finding("delivery", "There's no delivery confirmation yet — deadlines that count from delivery "
                                   "can't be confirmed until there is.", 0.4, ["delivery confirmation"])
    if ex == "dispute":
        if not case:
            return None
        from .agents import disputes

        cmp_ = disputes.compare(db, case)
        open_pts = [p["topic"] for p in cmp_["points"] if p["status"] in ("disputed", "claimed by one side", "unknown")]
        return Finding("dispute", "Still unconfirmed: " + ", ".join(open_pts) + "." if open_pts else "Nothing is in dispute.",
                       data=cmp_)
    if ex == "budget":
        amt = _amount(msg)
        if intent == "investment":
            st = budget_agent.status(db, uid)
            return Finding("budget", "", data=st)  # used by the investment expert; nothing extra to say
        if amt or intent == "price":
            if not amt and case:
                amt = case.amount
            if amt:
                w = budget_agent.what_if(db, uid, amt, label=f"a {money(amt)} purchase")
                return Finding("budget", w["message"], 0.7, [], data=w, primary=intent == "budget")
        st = budget_agent.status(db, uid)
        alerts = budget_agent.overspend_alerts(db, uid)
        if st["total_budget"]:
            from . import insights as _ins

            pc = _ins._pace(db, uid, datetime.now(UTC))
            pace = (f" At your usual pace (about {money(pc['rate'])} a day) you'll finish the month around "
                    f"{money(pc['projected'])} — " + (f"{money(-pc['over'])} under budget." if pc["over"] <= 0
                                                      else f"{money(pc['over'])} over, so ease off on {max(pc['per_cat'], key=pc['per_cat'].get) if pc['per_cat'] else 'extras'}."))
            head = (f"You've spent {money(st['month_spent'])} of your {money(st['total_budget'])} budget this month, "
                    f"so {money(st['remaining'])} is left." + pace)
        else:
            head = f"You've spent {money(st['month_spent'])} this month. You haven't set a budget yet."
        return Finding("budget", head + (" " + " ".join(alerts) if alerts else ""), 0.7,
                       ["accounts not connected to ContextIQ"], data=st, primary=True)
    if ex == "obligations":
        st = budget_agent.status(db, uid)
        bills = st["bills_before_payday"]
        if not bills:
            return Finding("obligations", "No bills are due before your next payday.")
        listing = ", ".join(f"{b['title']} ({money(b['amount'])}, {b['due']})" for b in bills)
        return Finding("obligations", f"Coming up before payday on {st['next_payday']}: {listing}.", data={"bills": bills})
    if ex == "invoice":
        return Finding("invoice", "Open Business → Check an invoice and paste the purchase order and the invoice. "
                                  "I'll compare every line before anything is paid.", primary=True)
    if ex == "fraud":
        risk = ctx_agent.assess_risk(db, uid, "unknown payee", _amount(msg) or 100, text=msg,
                                     payee_changed_recently=bool(re.search(r"bank details|new account", msg, re.I)))
        lead = {"allow": "Nothing here looks like a typical scam",
                "step_up": "Be careful — this has warning signs",
                "review": "This looks like a likely scam — don't pay yet"}[risk["decision"]]
        return Finding("fraud", f"{lead}: {'; '.join(risk['reasons'])}. Check with the payee using contact details you "
                                "already had — never the ones in the message.", 0.6, data=risk, primary=True)
    if ex == "subscription":
        subs = budget_agent.detect_subscriptions(db, uid)
        if not subs:
            return Finding("subscription", "I don't see any recurring payments yet.", primary=True)
        total = sum(s["amount"] * 30 / max(s["every_days"], 1) for s in subs)
        lst = "; ".join(f"{s['payee']} {money(s['amount'])} about every {s['every_days']} days (next around {s['next_expected']})"
                        for s in subs)
        return Finding("subscription", f"You have {len(subs)} recurring payment(s), about {money(total)} a month: {lst}.",
                       data={"subscriptions": subs}, primary=True)
    if ex == "investment":
        amt = _amount(msg) or 0.0
        out = investment.advise(db, uid, amt, horizon_months=60 if re.search(r"5 ?years?|long", msg, re.I) else 12)
        if not out.get("enabled"):
            return Finding("investment", out["message"], primary=True)
        return Finding("investment", out["liquidity"]["message"] + " " + out["disclaimer"], 0.6,
                       ["live market data (not connected)"], data=out, primary=True)
    if ex == "price":
        obs = []
        if case:
            obs = db.scalars(select(PriceObservation).where(PriceObservation.title.in_(case.title.split(", ")))
                             .order_by(PriceObservation.seen_at)).all()
        if len(obs) >= 2:
            prices = [o.price for o in obs]
            note = " — this is the lowest I've seen" if prices[-1] <= min(prices) else ""
            return Finding("price", f"I've seen {obs[-1].title} at {len(prices)} prices: lowest {money(min(prices))}, "
                                    f"latest {money(prices[-1])}{note}. I only report prices I've actually seen.",
                           data={"prices": prices}, primary=True)
        return Finding("price", "I haven't seen enough prices for that item yet to say if it's a good deal. "
                                "Visit it with the extension and I'll keep track.", 0.3, ["price history"], primary=True)
    return None


def bc_summary(db: Session, case: Case) -> dict:
    from .briefcase import case_summary

    return case_summary(db, case)


# which expert can fill which missing piece of evidence
FILLS = {"delivery_date": "delivery", "store policy": "policy", "policy_terms": "policy",
         "payment_captured": "payment", "paypal_state": "payment"}
PROVENANCE_RANK = {"verified": 3, "claimed": 2, "inferred": 1}
MAX_ROUNDS = 2


def reason(state: S) -> S:
    """Unified reasoning: merge uncertainty, detect gaps and contradictions, decide whether to gather more."""
    fs = state["findings"]
    done = {f.expert for f in fs}
    conf = min([f.confidence for f in fs if f.primary] or [1.0])
    unknowns = sorted({u for f in fs for u in f.unknowns})
    # gaps another expert could fill and hasn't tried yet
    want = sorted({FILLS[u] for u in unknowns if u in FILLS and FILLS[u] not in done})
    rounds = state.get("rounds", 0)
    contradictions, resolutions = [], list(state.get("resolutions") or [])
    pay = next((f for f in fs if f.expert == "payment"), None)
    disp = next((f for f in fs if f.expert == "dispute"), None)
    if pay and disp and pay.data.get("verdict") == "paid":
        if any(p["topic"] == "paid" and p["seller_says"] is False for p in disp.data.get("points", [])):
            contradictions.append("The seller says they weren't paid, but PayPal's record shows the payment completed.")
            resolutions.append("Conflict resolved in favour of PayPal's verified record over the seller's claim.")
    fraud = next((f for f in fs if f.expert == "fraud"), None)
    if fraud and pay and fraud.data.get("decision") == "review" and pay.data.get("verdict") == "paid":
        resolutions.append("Payment is complete, but the fraud expert flagged the payee — both are reported.")
    level = "high" if conf >= 0.85 else "medium" if conf >= 0.5 else "low"
    trace = [f"reasoning (round {rounds}): confidence {level}" + (f", missing {', '.join(unknowns)}" if unknowns else "")]
    if want and rounds < MAX_ROUNDS:
        trace.append(f"asking for more evidence from: {', '.join(want)}")
    return {"reasoning": {"confidence": round(conf, 2), "level": level, "unknowns": unknowns,
                          "contradictions": contradictions, "rounds": rounds},
            "requested": want if rounds < MAX_ROUNDS else [], "rounds": rounds + (1 if want else 0),
            "resolutions": resolutions, "trace": state["trace"] + trace}


def after_reason(state: S):
    return fan_out(state) if state.get("requested") else "decide"


def decide_node(state: S) -> S:
    """ContextIQ decision model ranks the permitted options any expert proposed."""
    from .intelligence.decision import decide as rank

    opts = [o for f in state["findings"] for o in (f.data.get("_options") or [])]
    if not opts:
        return {"decision": None}
    d = rank(opts)
    return {"decision": {k: v for k, v in d.items() if k != "ranked"} | {"ranked": d["ranked"]},
            "trace": state["trace"] + [f"decision model: {(d['choice'] or {}).get('name', 'none')} "
                                       f"(confidence {d['confidence']})"]}


def gate(state: S) -> S:
    """Approval checkpoint: a chosen action becomes a proposal; nothing executes from chat."""
    d = state.get("decision")
    prop = None
    if d and d.get("choice"):
        case_id = next((f.data.get("case_id") for f in state["findings"] if f.data.get("case_id")), None)
        prop = {"type": d["choice"]["name"], "case_id": case_id, "needs_approval": True,
                "how": "Nothing is sent or paid until you confirm on screen. Voice can't confirm money actions."}
    return {"proposal": prop, "trace": state["trace"] + (["approval needed before acting"] if prop else [])}


def respond(state: S) -> S:
    fs = state["findings"]
    if state["route_source"] == "unsure":
        alts = [INTENT_LABEL[state["intent"]]] + [INTENT_LABEL[a] for a in state.get("alternatives", [])[:1]]
        return {"answer": f"I'm not sure what you need. Is this about {alts[0]} or {alts[1]}?",
                "trace": state["trace"] + ["asked to clarify"]}
    primary = next((f for f in fs if f.primary), fs[0] if fs else None)
    parts = []
    ev = next((f for f in fs if f.expert == "evidence" and not f.primary and f.confidence > 0), None)
    if ev:
        parts.append(ev.summary)
    if primary:
        parts.append(primary.summary)
        d = state.get("decision")
        if d and d.get("choice"):
            ch = d["choice"]
            parts.append(f"My suggestion: {nice(ch['name'])} — {ch['explanation'].lower()}."
                         + (" It's a close call, so check the options." if d.get("confidence") == "low" else ""))
    for f in fs:
        if f is primary or f is ev or not f.summary or f.expert == "dispute":
            continue
        parts.append(f.summary)
    r = state["reasoning"]
    parts += r["contradictions"]
    if state["proposal"]:
        parts.append("I've prepared it — tap Confirm when you're ready. Nothing happens until you do.")
    answer = " ".join(p.strip() for p in parts if p)
    if llm.available() and state["intent"] in ("refund", "payment_status", "fraud", "investment"):
        answer = llm.humanize(answer)
    return {"answer": answer, "trace": state["trace"] + ["answer written"]}


def _build():
    g = StateGraph(S)
    g.add_node("understand", understand)
    g.add_node("plan", plan)
    g.add_node("expert", expert)          # runs once per expert, in parallel (Send fan-out)
    g.add_node("reason", reason)          # unified reasoning; may loop back for more evidence
    g.add_node("decide", decide_node)     # ContextIQ decision model
    g.add_node("gate", gate)              # approval checkpoint
    g.add_node("respond", respond)
    g.set_entry_point("understand")
    g.add_conditional_edges("understand", lambda s: "respond" if s["route_source"] == "unsure" else "plan",
                            ["respond", "plan"])
    g.add_conditional_edges("plan", fan_out, ["expert"])
    g.add_edge("expert", "reason")
    g.add_conditional_edges("reason", after_reason, ["expert", "decide"])
    g.add_edge("decide", "gate")
    g.add_edge("gate", "respond")
    g.add_edge("respond", END)
    return g.compile()


GRAPH = _build()


def handle(db: Session, user_id: str, message: str, case_id: str | None = None, voice: bool = False) -> dict:
    t0 = time.time()
    tokens_before = llm.METER["input_tokens"] + llm.METER["output_tokens"]
    if not FRAUD_SAFETY_RE.search(message):
        top, p = runtime.route_intent(message)
        if off_topic(message, p):
            return {"answer": ("That's outside what I can help with. I'm ContextIQ, your payments assistant: ask me "
                               "about a purchase, a refund, your budget, bills, an invoice or a payment that looks wrong."),
                    "intent": "off_topic", "topic": "something outside payments", "route_source": "out of scope",
                    "confidence": round(1 - p, 3), "case_id": None, "experts": [], "reasoning": None, "proposal": None,
                    "findings": [], "decision": None, "resolutions": [], "evidence_rounds": 0,
                    "trace": [f"out of scope (router's best guess {top} at {p:.2f}, no payments topic in the message)"],
                    "latency_ms": round((time.time() - t0) * 1000, 1), "llm_tokens": 0, "llm": llm.provider_name()}
    out = GRAPH.invoke({"db": db, "user_id": user_id, "message": message, "case_id": case_id, "trace": [],
                        "findings": [], "rounds": 0, "requested": [], "resolutions": [], "decision": None,
                        "reasoning": {"confidence": 1.0, "level": "high", "unknowns": [], "contradictions": [],
                                      "rounds": 0}, "proposal": None, "plan": []})
    db.expire_all()  # experts wrote evidence in their own sessions
    case = out.get("case")
    findings = out.get("findings", [])
    return {"answer": out["answer"], "intent": out["intent"], "topic": INTENT_LABEL[out["intent"]],
            "route_source": out["route_source"], "confidence": round(out["confidence"], 3),
            "case_id": case.id if case else None, "experts": out.get("plan", []),
            "reasoning": out.get("reasoning"), "proposal": out.get("proposal"),
            "findings": [{k: v for k, v in asdict(f).items() if k not in ("data", "decision")} for f in findings],
            "decision": out.get("decision"), "resolutions": out.get("resolutions", []),
            "evidence_rounds": out.get("reasoning", {}).get("rounds", 0),
            "trace": out["trace"], "latency_ms": round((time.time() - t0) * 1000, 1),
            "llm_tokens": llm.METER["input_tokens"] + llm.METER["output_tokens"] - tokens_before,
            "llm": llm.provider_name()}
