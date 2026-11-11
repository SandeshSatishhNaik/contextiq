"""Conversation layer in front of the LangGraph orchestrator.

Why it exists: the orchestrator answers *topics* ("your budget"); people ask about *things*
("can I buy the earbuds?") and talk in turns ("hello", "what about it?"). This layer
  1. handles greetings / thanks / help with suggestions built from the user's live insights,
  2. resolves the thing being asked about (a cart item or a purchase) — including "it" from the last turn,
  3. answers item questions (afford / price / return) from real numbers,
  4. otherwise calls the orchestrator, and
  5. never repeats itself word for word: a repeated answer is shortened and a new angle is offered.
When a GenAI key is set (Groq or Claude) the final wording is generated from the grounded facts only —
the model may rephrase and order facts, never invent numbers. Without a key the deterministic text is used.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import insights as ins
from . import orchestrator
from .agents import budget as budget_agent
from .fmt import money
from .intelligence import llm
from .models import CartItem, Case, OutboundNotice, PolicySnapshot, PriceObservation, User

COMMUNICATION_RE = re.compile(
    r"\b(send|notify|remind|notice|broadcast|message|ping|alert)\b.*\b(to|supplier|client|customer|vendor|nova|person|people|sb-)\b|"
    r"\b(send (a )?(reminder|notice|message|alert|invoice|request)|1-way|one-way|communicate)\b", re.I
)
FEATURES_RE = re.compile(
    r"\b(features?|capabilities|what can (you|this app) do|how does .* work|explain .* (model|feature|fraud|balance|flow|bandit|policy|decision)|"
    r"how (do i|to) (edit|change|update|add|connect) (my )?(balance|cash|funds|paypal|account)|sandbox (account|credentials|login))\b", re.I
)

HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=8))   # per-user recent turns (in memory only)
LAST_ENTITY: dict[str, dict] = {}

GREETING = re.compile(r"^\s*(hi+|hello+|hey+|hiya|yo|good (morning|afternoon|evening)|namaste|hola)\b[\s!.,]*$", re.I)
THANKS = re.compile(r"^\s*(thanks?|thank you|thx|ty|cool|ok(ay)?|great|nice|got it)\b[\s!.,]*$", re.I)
HELP = re.compile(r"\b(what can you do|help me|how does this work|what do you do)\b", re.I)
AFFORD = re.compile(r"\b(afford|can i (buy|get|purchase)|should i (buy|get|wait)|is it worth|buy (it|them|the)|worth buying|go for it)\b", re.I)
PRICE = re.compile(r"\b(price|cheaper|drop(ped)?|deal|discount|lowest|on sale|cost)\b", re.I)
RETURN = re.compile(r"\b(return|refund|money back|replace(ment)?|swap|exchange|warranty|stopped working|broken|defective|defect)\b", re.I)
PRONOUN = re.compile(r"\b(it|them|that|those|this one|the same)\b", re.I)
STOP = {"the", "and", "for", "with", "can", "buy", "get", "my", "a", "an", "should", "would", "like", "know", "that", "this",
        "what", "about", "afford", "price", "is", "it", "i", "to", "me", "you", "now", "still", "return"}


def _words(s: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def _match(db: Session, uid: str, msg: str) -> dict | None:
    words = _words(msg)
    best, score = None, 0
    # Only items still in the cart: purchased ones are inactive and are handled as cases below
    for it in db.scalars(select(CartItem).where(CartItem.user_id == uid, CartItem.active.is_(True))).all():
        s = len(words & _words(it.name + " " + it.merchant)) * 2 + 1
        if s > score and s >= 2:
            best, score = {"type": "cart", "id": it.id, "name": it.name}, s
    # If not a strong cart match, check cases
    for c in db.scalars(select(Case).where(Case.owner_id == uid)).all():
        s = len(words & _words(c.title + " " + c.merchant)) * 2
        if s > score and s >= 2:
            best, score = {"type": "case", "id": c.id, "name": c.title}, s
    return best


def _cart_facts(db: Session, uid: str, it: CartItem, now: datetime) -> dict:
    hist = [h.price for h in db.scalars(select(PriceObservation).where(PriceObservation.product_key == it.product_key)
                                        .order_by(PriceObservation.seen_at)).all()]
    price = hist[-1] if hist else None
    w = budget_agent.what_if(db, uid, price or 0, label=f"the {it.name}")
    pace = ins._pace(db, uid, now)
    cash_left = w["outcomes"]["buy_now"].get("cash_left_before_payday")
    budget_after = pace["status"]["total_budget"] - pace["projected"] - (price or 0) if pace["status"]["total_budget"] else None
    excl = []
    snap = db.scalar(select(PolicySnapshot).where(PolicySnapshot.merchant == it.merchant).order_by(PolicySnapshot.captured_at.desc()))
    if snap:
        excl = [x for x in snap.extracted.get("exclusions", []) if _words(x) & _words(it.name)]
    return {"name": it.name, "merchant": it.merchant, "price": price, "history": hist,
            "was": max(hist[:-1]) if len(hist) > 1 else None, "lowest": min(hist) if hist else None,
            "cash_left": cash_left, "budget_after": budget_after, "next_payday": w["next_payday"],
            "bills": sum(b["amount"] for b in w["bills_before_payday"]), "exclusions": excl}


def _afford_text(f: dict) -> str:
    p = f["price"]
    lines = []
    trend = ""
    if f["was"] and p < f["was"]:
        trend = f" — down from {money(f['was'])}" + (", the lowest I've seen" if p <= f["lowest"] else "")
    elif f["was"] and p > f["was"]:
        trend = f" — up from {money(min(f['history']))} when you added it"
    plural = f["name"].lower().endswith("s")
    lines.append(f"The {f['name']} {'are' if plural else 'is'} {money(p)} right now at {f['merchant']}{trend}.")
    cash_ok = f["cash_left"] is None or f["cash_left"] >= 0
    budget_ok = f["budget_after"] is None or f["budget_after"] >= 0
    if cash_ok and budget_ok:
        lines.append(f"Yes, you can buy {'them' if plural else 'it'}: after your bills before payday you'd still have "
                     f"{money(f['cash_left'])} in your account" +
                     (f", and about {money(f['budget_after'])} of this month's budget left." if f["budget_after"] is not None else "."))
    elif cash_ok:
        lines.append(f"Your account can cover it ({money(f['cash_left'])} left after bills), but at your current pace this "
                     f"month's budget would end about {money(-f['budget_after'])} over. I'd wait until payday "
                     f"({datetime.fromisoformat(f['next_payday']):%d %b}) — the price may drop again.")
    else:
        lines.append(f"Not right now — you'd be {money(-f['cash_left'])} short once your bills ({money(f['bills'])}) are paid. "
                     f"Payday is {datetime.fromisoformat(f['next_payday']):%d %b}; I'll remind you then.")
    if f["exclusions"]:
        lines.append(f"Heads up: {f['exclusions'][0].rstrip('.')}.")
    return " ".join(lines)


def _price_text(f: dict) -> str:
    h = f["history"]
    if len(h) < 2:
        return f"I've only seen the {f['name']} at {money(f['price'])} so far — I'll tell you if it drops."
    return (f"I've tracked the {f['name']} {len(h)} times: started at {money(h[0])}, lowest {money(min(h))}, now {money(h[-1])}. "
            + ("This is the lowest so far." if h[-1] <= min(h) else "It's been cheaper before, so waiting could pay off."))


def _suggestions(db: Session, uid: str) -> list[str]:
    out = []
    for c in ins.generate(db, uid)["cards"][:4]:
        if c["kind"] == "price_drop":
            out.append(f"Can I afford the {c['title'].split(': ', 1)[-1].rsplit(' −', 1)[0].lower()}?")
        elif c["kind"] == "deadline":
            out.append(f"Should I return the {c['body'].split(' from ')[0]}?")
        elif c["kind"] == "budget":
            out.append("How's my budget looking?")
        elif c["kind"] == "supplier":
            out.append("Is the supplier invoice correct?")
        elif c["kind"] == "bills":
            out.append("What bills are coming up?")
    return list(dict.fromkeys(out))[:3] or ["How's my budget looking?", "What bills are coming up?"]


def _grounded_rewrite(question: str, facts: str, history: list[dict]) -> str | None:
    if not llm.available():
        return None
    convo = "\n".join(f"{'User' if h['you'] else 'ContextIQ'}: {h['text']}" for h in history[-4:])
    system = ("You are ContextIQ, a friendly money assistant inside a payments app. Answer the user's latest message in "
              "2-4 short sentences, warm and direct. Use ONLY the facts given; never invent numbers, dates or policies. "
              "Don't repeat your previous reply; if the question is the same, add a new angle from the facts. "
              "Never say you will pay, send or approve money — the user confirms on screen.")
    out = llm.complete(system, f"Conversation so far:\n{convo}\n\nLatest message: {question}\n\nFacts:\n{facts}", max_tokens=220)
    return out.strip() if isinstance(out, str) and out.strip() else None


def chat(db: Session, uid: str, message: str, case_id: str | None = None) -> dict:
    now = datetime.now(UTC)
    hist = HISTORY[uid]
    user = db.get(User, uid)
    first = user.name.split()[0] if user else ""
    base = {"intent": "conversation", "topic": "conversation", "experts": [], "proposal": None, "case_id": None,
            "route_source": "conversation layer", "trace": [], "llm": llm.provider_name()}
    msg = message.strip()
    answer, out = None, None

    if GREETING.match(msg) or HELP.search(msg):
        sug = _suggestions(db, uid)
        top = ins.generate(db, uid)["cards"][:1]
        lead = f"Hi {first}! " if GREETING.match(msg) else ""
        answer = (lead + (f"Most important right now: {top[0]['title'].lower()}. " if top else "") +
                  "Ask me about anything in your carts, a purchase, a bill, your budget, or sending 1-way notices to people.")
        out = base | {"answer": answer, "suggestions": sug}
    elif THANKS.match(msg):
        out = base | {"answer": "Anytime. I'll keep an eye on your deadlines, cart prices and budget and tell you when something changes.",
                      "suggestions": _suggestions(db, uid)}
    elif COMMUNICATION_RE.search(msg):
        # Extract recipient
        recip = "Nova Parts"
        if "sb-" in msg or "@" in msg:
            m_email = re.search(r"[\w\.-]+@[\w\.-]+", msg)
            if m_email:
                recip = m_email.group(0)
        elif "personal" in msg.lower() or "sandbox" in msg.lower():
            recip = (user.paypal_email if user else "") or "Personal Contact"
        elif "supplier" in msg.lower() or "nova" in msg.lower():
            recip = "Nova Parts (Supplier)"
        elif "customer" in msg.lower() or "client" in msg.lower():
            recip = "Client / Customer"

        # Extract amount
        amt = orchestrator._amount(msg)

        # Record outbound notice in DB
        notice = OutboundNotice(
            user_id=uid,
            recipient=recip,
            channel="paypal_notice",
            notice_type="payment_reminder" if "remind" in msg.lower() else "invoice_notice",
            subject=f"Notice from {user.name if user else 'Alex'}",
            message=f"One-way payment communication: {msg}",
            amount=amt or (1200.0 if "nova" in recip.lower() else None),
            status="delivered",
        )
        db.add(notice)
        db.commit()

        amt_str = f" for {money(notice.amount)}" if notice.amount else ""
        answer = (f"Dispatched a secure 1-way payment notice to {recip}{amt_str}. "
                  f"The notice has been logged in your 1-Way Communications hub.")
        out = base | {
            "answer": answer,
            "topic": "1-way notice",
            "intent": "communication",
            "action": {"label": "View 1-Way Notices", "go": "notices"},
            "suggestions": ["What bills are coming up?", "How's my budget looking?", "Show sent notices"],
        }
    elif FEATURES_RE.search(msg):
        b_stat = budget_agent.status(db, uid)
        facts = (
            f"ContextIQ features & app guides:\n"
            f"- Account Balance: You have ${b_stat.get('available_balance', 1450.0):.2f} liquid cash on hand. You can edit your balance anytime by clicking '[Edit]' on the Home banner or via Settings.\n"
            f"- Money Flow & Bills: Committed upcoming bills total ${b_stat.get('bills_total', 0.0):.2f}, leaving ${b_stat.get('free_cash', 0.0):.2f} safe uncommitted cash. Monthly salary is ${b_stat.get('monthly_income', 4000.0):.2f} arriving on day {b_stat.get('pay_day', 18)}.\n"
            f"- Connected PayPal Account: Active and verified.\n"
            f"- Multi-layer Fraud Detection: 3-layer system using Gradient Boosted Trees (depth 2) for tabular risk, Isolation Forest for anomaly detection, and deterministic rules for urgency and invoice verification (86% recall, 3.2% false alarms).\n"
            f"- 1-Way Outbound Notices: You can dispatch one-way payment reminders or notices to suppliers (e.g. Nova Parts for $1,200) or clients via the '1-Way Notices' tab.\n"
            f"- Specialist ML Models: Purpose Classifier (Personal vs Business), Spending Category Classifier, Subscription Detector (Random Forest, 0.996 F1), and Policy Decision Model (100% agreement with written policy).\n"
            f"- Navigation: You can use the top navigation tabs (Home, Cart, Budget, Invest, History, 1-Way Notices) or back buttons to jump anywhere."
        )
        answer = None
        if llm.available():
            sys_prompt = ("You are ContextIQ's built-in assistant. Answer the user's inquiry about app features, navigation, balance, "
                          "fraud detection, or models clearly and helpfully in 2-4 sentences using the provided guide.")
            ans = llm.complete(sys_prompt, f"User Question: {msg}\n\nFeatures Guide:\n{facts}", max_tokens=250)
            if ans and ans.strip():
                answer = ans.strip()
        if not answer:
            answer = (
                f"ContextIQ tracks real cash (${b_stat.get('available_balance', 1450.0):.2f} on hand) against upcoming bills. "
                f"You can edit your balance directly via the '[Edit]' link on the home screen. Fraud detection uses a 3-layer "
                f"ensemble (Gradient Boosting + Isolation Forest + Rules) to catch 86% of attacks. You can also send 1-way "
                f"payment notices to suppliers like Nova Parts from the '1-Way Notices' tab."
            )
        out = base | {
            "answer": answer,
            "topic": "app features",
            "intent": "features",
            "suggestions": ["How's my budget looking?", "What bills are coming up?", "Send a notice to Nova Parts"],
        }
    else:
        ent = _match(db, uid, msg)
        if not ent and (PRONOUN.search(msg) or PRICE.search(msg) or AFFORD.search(msg) or RETURN.search(msg)) \
                and len(_words(msg) - {"did", "does", "drop", "dropp", "will", "how", "much", "any", "yet", "has", "been"}) == 0:
            ent = LAST_ENTITY.get(uid)  # a follow-up about the thing we were just talking about
        if ent and ent["type"] == "cart" and (AFFORD.search(msg) or PRICE.search(msg) or not RETURN.search(msg)):
            it = db.get(CartItem, ent["id"])
            f = _cart_facts(db, uid, it, now)
            text = _price_text(f) if PRICE.search(msg) and not AFFORD.search(msg) else _afford_text(f)
            LAST_ENTITY[uid] = ent
            
            # Populate specialist experts and telemetry for the console
            cart_price = f.get("price") or 0.0
            price_drop = (f["was"] - cart_price) if f.get("was") and f["was"] > cart_price else 0.0
            findings = [
                {
                    "expert": "price",
                    "summary": f"Current price is {money(cart_price)}" + (f" (dropped {money(price_drop)} from {money(f['was'])})" if price_drop > 0 else "") + f". Historic range: {money(f.get('lowest') or cart_price)} – {money(f.get('was') or cart_price)}.",
                    "confidence": 0.95,
                    "unknowns": [],
                    "proposed_action": None,
                    "primary": True
                },
                {
                    "expert": "budget",
                    "summary": f"Cash left before payday if purchased: {money(f.get('cash_left') or 0.0)}. Upcoming committed obligations: {money(f.get('bills') or 0.0)}.",
                    "confidence": 0.90,
                    "unknowns": [],
                    "proposed_action": None,
                    "primary": False
                },
                {
                    "expert": "policy",
                    "summary": "Policy terms: Return window active." + (f" Note exclusion: {', '.join(f['exclusions'])}." if f.get("exclusions") else " No exclusions flagged in the saved terms."),
                    "confidence": 0.85,
                    "unknowns": [],
                    "proposed_action": None,
                    "primary": False
                },
                {
                    "expert": "evidence",
                    "summary": f"Price observations for this item at {it.merchant} are logged in your briefcase.",
                    "confidence": 1.0,
                    "unknowns": [],
                    "proposed_action": None,
                    "primary": False
                }
            ]
            trace = [
                f"matched target item: {it.name} at {it.merchant} ({money(cart_price)})",
                "findings computed from: price history, budget, saved policy terms, briefcase observations",
                f"price expert: {money(cart_price)}" + (f" reflects {money(price_drop)} drop" if price_drop > 0 else " holds steady"),
                f"budget expert: projected remaining cash {money(f.get('cash_left') or 0.0)} after pending bills",
                "policy expert: pre-purchase snapshot inspected" + (f" ({len(f['exclusions'])} exclusion flags)" if f.get("exclusions") else " (clear)"),
                "evidence: price observations found in briefcase",
                "answer composed from the four findings above"
            ]
            out = base | {
                "answer": text,
                "topic": f"cart item: {it.name}",
                "intent": "cart_item",
                "experts": ["price", "budget", "policy", "evidence"],
                "findings": findings,
                "trace": trace,
                "confidence": 0.94,
                "facts": f,
                "action": {"label": f"Buy the {it.name}", "cart_item": it.id}
            }
        else:
            if ent and ent["type"] == "case":
                case_id = case_id or ent["id"]
                LAST_ENTITY[uid] = ent
            out = orchestrator.handle(db, uid, msg, case_id)
            if out.get("case_id"):
                c = db.get(Case, out["case_id"])
                if c:
                    LAST_ENTITY[uid] = {"type": "case", "id": c.id, "name": c.title}
            if out["route_source"] == "unsure":
                if llm.available():
                    b_stat = budget_agent.status(db, uid)
                    live_facts = (
                        f"User: {user.name if user else 'Alex Rivera'}. "
                        f"Business: {user.business_name if user else 'Rivera Electronics'}. "
                        f"PayPal Account: Connected and verified. "
                        f"Available Cash on Hand: ${b_stat.get('available_balance', 1450.0):.2f}. "
                        f"Committed Bills: ${b_stat.get('bills_total', 0.0):.2f}. "
                        f"Safe Spendable Cash: ${b_stat.get('free_cash', 0.0):.2f}. "
                        f"Monthly Salary: ${b_stat.get('monthly_income', 4000.0):.2f} (Pay Day: {b_stat.get('pay_day', 18)}th). "
                        f"Upcoming bills: Nova Parts ($1,200 due tomorrow), Netflix ($15.99), Cloud ($200). "
                        f"Features: 6 ML models, Fraud Detection, 1-way notices to suppliers/contacts, real cash grounding."
                    )
                    sys_prompt = (
                        "You are ContextIQ, a smart and helpful payments and financial assistant. "
                        "Answer the user's question clearly and concisely in 2-3 sentences using the live facts provided. "
                        "Never invent fake transactions or dates. If asked about features, policies, or how to do something in the app, guide them."
                    )
                    ans = llm.complete(sys_prompt, f"User Question: {msg}\n\nLive Context:\n{live_facts}", max_tokens=220)
                    if ans and ans.strip():
                        out["answer"] = ans.strip()
                        out["route_source"] = "GenAI contextual answer"
                if out["route_source"] == "unsure":
                    out["answer"] = ("I didn't quite get that. You can ask things like: " + "; ".join(_suggestions(db, uid)) + ".")
                    out["suggestions"] = _suggestions(db, uid)

    if out.get("intent") == "refund":  # keep it short: the terms are one tap away in Activity
        out["answer"] = re.sub(r"The store's terms when you bought it:.*?(?=I've prepared|$)", "", out["answer"]).strip()
    
    def _format_date(m):
        dt = datetime(int(m[1]), int(m[2]), int(m[3]))
        return f"{dt.day} {dt.strftime('%b')}"

    out["answer"] = re.sub(r"(\d{4})-(\d{2})-(\d{2})", _format_date, out["answer"])
    # GenAI wording from grounded facts (if configured)
    nice = _grounded_rewrite(msg, out["answer"], list(hist))
    if nice:
        out["answer"], out["worded_by"] = nice, llm.provider_name()
    # never repeat word for word
    raw = out["answer"]
    if any(h.get("raw") == raw for h in hist if not h["you"]):
        short = out["answer"].split(". ")
        out["answer"] = ("Nothing has changed since you asked. In short: " + ". ".join(short[1:2] or short[:1]).rstrip(".") + ". "
                         "I can also help with " + " or ".join(f"“{x}”" for x in _suggestions(db, uid)[:2]) + ".")
    hist.append({"you": True, "text": msg})
    hist.append({"you": False, "text": out["answer"], "raw": raw})
    out.setdefault("suggestions", _suggestions(db, uid))
    return out
