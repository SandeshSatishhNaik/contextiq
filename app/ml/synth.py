"""Synthetic data generators (clearly synthetic; seeded for reproducibility).

Normal behaviour only. Attacks live in redteam.py, written separately so the fraud
model is evaluated on attack families it never saw during training.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 7

PERSONAL_MERCHANTS = {
    "groceries": ["FreshMart", "GreenGrocer", "DailyBasket", "CityMarket"],
    "dining": ["Bistro 21", "Noodle House", "Cafe Aroma", "Pizza Point"],
    "entertainment": ["StreamFlix", "TuneBox", "CineWorld", "GameHub"],
    "electronics": ["TechKart", "GadgetZone", "SoundWave Store"],
    "transport": ["MetroRide", "QuickCab", "FuelUp"],
    "health": ["CarePharmacy", "FitClub"],
    "clothing": ["UrbanWear", "StyleLane"],
    "utilities": ["PowerGrid Co", "AquaWorks", "NetFiber"],
}
BUSINESS_MERCHANTS = {
    "supplies": ["OfficeDepot Pro", "PaperCraft Supply", "DeskWorks"],
    "inventory": ["Global Components Ltd", "Shenzhen Parts Co", "Allied Wholesale"],
    "software": ["CloudHost", "DevTools Inc", "CRMly"],
    "logistics": ["ShipFast Freight", "CargoLink"],
    "services": ["Legal Partners LLP", "Ledger Accountants", "AdReach Media"],
}
CATEGORY_AMOUNT = {  # (median, sigma) for a lognormal
    "groceries": (45, 0.5), "dining": (25, 0.5), "entertainment": (15, 0.4), "electronics": (180, 0.8),
    "transport": (20, 0.6), "health": (40, 0.6), "clothing": (60, 0.6), "utilities": (70, 0.3),
    "supplies": (120, 0.6), "inventory": (1500, 0.7), "software": (90, 0.5), "logistics": (300, 0.6),
    "services": (600, 0.5),
}
PERSONAL_DESC = ["weekly shop", "dinner", "monthly plan", "headphones", "ride home", "medicine", "new shoes",
                 "electricity bill", "groceries", "movie tickets", "gift for friend", "phone charger"]
BUSINESS_DESC = ["invoice payment", "office supplies", "PO restock", "server hosting", "freight charges",
                 "consulting retainer", "bulk components", "client ads", "printer toner", "laptop for office"]


_PREFIX = ["Prime", "Metro", "Blue", "Sun", "North", "Urban", "Bright", "Star", "Royal", "Green", "Nova", "Apex"]
_SUFFIX = {
    "groceries": ["Mart", "Grocers", "Market", "Foods"], "dining": ["Kitchen", "Cafe", "Diner", "Grill"],
    "entertainment": ["Stream", "Cinemas", "Games", "Music"], "electronics": ["Electronics", "Gadgets", "Tech"],
    "transport": ["Rides", "Cabs", "Fuel"], "health": ["Pharmacy", "Clinic", "Fitness"],
    "clothing": ["Apparel", "Fashion", "Wear"], "utilities": ["Power", "Water", "Broadband"],
    "supplies": ["Office Supply", "Stationers", "Supplies Co"], "inventory": ["Components Ltd", "Wholesale", "Parts Co"],
    "software": ["Cloud", "Software Inc", "SaaS"], "logistics": ["Freight", "Logistics", "Couriers"],
    "services": ["Consulting", "Legal LLP", "Accountants"],
}


_PREFIX_UNSEEN = ["Shree", "Lakshmi", "Coastal", "Harbor", "Vertex", "Maple", "Sapphire", "Kaveri", "Orbit", "Pioneer"]


def merchant_universe(seed: int = RNG_SEED, prefixes: list[str] | None = None) -> dict[str, list[str]]:
    """Procedural merchant names so the test set can contain merchants never seen in training."""
    rng = np.random.default_rng(seed + 9)
    out = {}
    for cat, sufs in _SUFFIX.items():
        names = {f"{p} {s}" for p in (prefixes or _PREFIX) for s in sufs}
        base = PERSONAL_MERCHANTS.get(cat, []) + BUSINESS_MERCHANTS.get(cat, [])
        out[cat] = (base if prefixes is None else []) + sorted(rng.permutation(sorted(names))[:10].tolist())
    return out


def _amount(rng, category: str) -> float:
    med, sig = CATEGORY_AMOUNT[category]
    return float(np.round(rng.lognormal(np.log(med), sig), 2))


def _price_point(rng, x: float) -> float:
    r = rng.random()
    if r < 0.35:
        return round(np.floor(x) + 0.99, 2)
    if r < 0.5:
        return round(np.floor(x) + 0.49, 2)
    if r < 0.7:
        return float(round(x))
    return round(x, 2)


def make_users(n: int = 120, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        is_owner = rng.random() < 0.45
        start = int(rng.choice([7, 8, 9, 10]))
        rows.append({"user_id": f"u{i:03d}", "business_owner": is_owner, "work_start": start,
                     "work_end": start + int(rng.choice([8, 9, 10])), "night_owl": rng.random() < 0.2,
                     "spend_scale": float(rng.lognormal(0, 0.35))})
    return pd.DataFrame(rows)


def make_transactions(users: pd.DataFrame, days: int = 120, seed: int = RNG_SEED,
                      merchant_prefixes: list[str] | None = None, night_business: float = 0.0) -> pd.DataFrame:
    """Normal transactions with label columns: purpose, category. Includes realistic noise
    (business purchases at 8 PM from home, personal purchases at work, legit new payees)."""
    rng = np.random.default_rng(seed + 1)
    merchants = merchant_universe(seed, merchant_prefixes)
    shared_desc = ["order", "purchase", "payment", "monthly", "online order", "receipt"]
    rows = []
    for u in users.itertuples():
        n = int(rng.poisson(days * (1.4 if u.business_owner else 0.9)))
        for _ in range(n):
            business = u.business_owner and rng.random() < 0.38
            if business:
                cat = str(rng.choice(list(BUSINESS_MERCHANTS) + ["electronics", "dining", "transport"]))
                desc = str(rng.choice(BUSINESS_DESC + shared_desc + ["client lunch", "taxi to client"]))
                in_hours = rng.random() < 0.7
            else:
                cat = str(rng.choice(list(PERSONAL_MERCHANTS) + ["supplies", "software"]))
                desc = str(rng.choice(PERSONAL_DESC + shared_desc))
                in_hours = rng.random() < 0.35
            payee = str(rng.choice(merchants[cat]))
            # ambiguous overlap: electronics bought for the office
            if cat == "electronics" and u.business_owner and rng.random() < 0.3:
                business, desc = True, str(rng.choice(["laptop for office", "purchase", "order"]))
            hour = int(rng.integers(u.work_start, u.work_end)) if in_hours else int(
                rng.choice(list(range(6, u.work_start)) + list(range(u.work_end, 24)) or [20]))
            if u.night_owl and rng.random() < 0.3:
                hour = int(rng.choice([0, 1, 2, 23]))
            if business and rng.random() < night_business:  # e.g. paying suppliers at night from home
                hour = int(rng.choice([20, 21, 22, 23]))
            day = int(rng.integers(0, days))
            weekday = day % 7
            if cat == "dining" and rng.random() < 0.4:  # people eat out more at weekends
                weekday = int(rng.choice([5, 6]))
            if rng.random() < 0.03:  # people mis-file things; real labels are noisy
                business = not business if u.business_owner else business
            rows.append({
                "user_id": u.user_id, "day": day, "hour": hour,
                "weekday": weekday, "payee": payee, "description": desc, "category": cat,
                "purpose": "business" if business else "personal",
                # retail prices cluster at .99 / .49 / round numbers
                "amount": _price_point(rng, _amount(rng, cat) * u.spend_scale * (1.25 if day % 30 < 3 else 1.0)),
                "channel": str(rng.choice(["online", "in_person", "invoice"] if business else ["online", "in_person"])),
                "business_owner": u.business_owner,
            })
    return pd.DataFrame(rows).sort_values(["user_id", "day", "hour"]).reset_index(drop=True)


# ----------------------------------------------------------------- fraud features
FRAUD_FEATURES = ["amount_z", "log_amount", "new_payee", "payee_changed_recently", "new_device",
                  "ip_country_mismatch", "unusual_hour", "burst_1h", "invoice_po_ratio", "urgency_score",
                  "session_age_min"]
URGENT_WORDS = ["urgent", "immediately", "today only", "final notice", "account suspended", "act now",
                "new bank details", "wire now", "avoid penalty", "confidential"]


def urgency_score(text: str) -> float:
    t = text.lower()
    return min(1.0, sum(w in t for w in URGENT_WORDS) / 2.0)


def normal_fraud_rows(n: int = 12000, seed: int = RNG_SEED) -> pd.DataFrame:
    """Legitimate sessions, with the noise that causes false positives in real systems."""
    rng = np.random.default_rng(seed + 2)
    amount_z = rng.normal(0, 1, n)
    big = rng.random(n) < 0.04  # legit large purchases (a TV, annual plan)
    amount_z[big] = rng.uniform(2.0, 4.5, big.sum())
    texts = rng.choice(["thanks for your order", "monthly invoice", "receipt", "your booking",
                        "please pay by friday", "reminder: invoice due", "order confirmed",
                        "urgent: invoice due today", "final notice for overdue bill"], n,
                       p=[0.16, 0.16, 0.16, 0.16, 0.12, 0.12, 0.08, 0.03, 0.01])
    return pd.DataFrame({
        "amount_z": amount_z,
        "log_amount": rng.normal(4.0, 1.0, n),
        "new_payee": (rng.random(n) < 0.12).astype(int),
        "payee_changed_recently": (rng.random(n) < 0.01).astype(int),  # legit bank changes happen
        "new_device": (rng.random(n) < 0.06).astype(int),  # new phone, travel
        "ip_country_mismatch": (rng.random(n) < 0.03).astype(int),
        "unusual_hour": (rng.random(n) < 0.08).astype(int),
        "burst_1h": rng.poisson(0.4, n),
        # most invoices match; a few legit ones differ (agreed extras, freight added later)
        "invoice_po_ratio": np.where(rng.random(n) < 0.15, rng.uniform(0.98, 1.03, n),
                                     np.where(rng.random(n) < 0.01, rng.uniform(1.05, 1.12, n), 1.0)),
        "urgency_score": [urgency_score(t) for t in texts],
        "session_age_min": rng.exponential(40, n),
        "family": "normal",
        "label": 0,
    })


# --------------------------------------------------------------- subscriptions
def make_payee_series(n_series: int = 3000, seed: int = RNG_SEED, utility_share: float = 0.15) -> pd.DataFrame:
    """One row per (user, payee) history with summary features; label recurring or not.
    Recurring includes fixed-price subscriptions AND monthly bills whose amount varies (electricity)."""
    rng = np.random.default_rng(seed + 3)
    rows = []
    for _ in range(n_series):
        recurring = rng.random() < 0.4
        if recurring and rng.random() < utility_share:
            k = int(rng.integers(4, 12))
            days = np.cumsum(np.maximum(1, rng.normal(30, 1.5, k)))
            amounts = rng.lognormal(np.log(70), 0.22, k)  # same biller every month, amount moves with usage
        elif recurring:
            period = float(rng.choice([7, 30, 30, 30, 365 / 4, 365]))
            k = int(rng.integers(3, 12))
            days = np.cumsum(np.maximum(1, rng.normal(period, period * 0.06, k)))
            if rng.random() < 0.15 and k > 4:  # a missed or failed payment
                days = np.delete(days, int(rng.integers(1, k - 1)))
            base = rng.lognormal(np.log(15), 0.8)
            amounts = base * (1 + rng.normal(0, 0.02, len(days)))
            if rng.random() < 0.2:  # price change mid-way (plan upgrade)
                amounts[len(days) // 2:] *= rng.uniform(1.1, 1.4)
        elif rng.random() < 0.45:
            # hard negative: habitual shopping (weekly groceries, fuel) — regular-ish but not a subscription
            k = int(rng.integers(4, 20))
            days = np.cumsum(np.maximum(1, rng.normal(7, rng.uniform(1.5, 3.5), k)))
            amounts = rng.lognormal(np.log(45), rng.uniform(0.2, 0.5), k)
        else:
            k = int(rng.integers(2, 12))
            days = np.sort(rng.uniform(0, 180, k))
            amounts = rng.lognormal(np.log(40), 0.6, k)
        rows.append(series_features(days, amounts) | {"label": int(recurring)})
    return pd.DataFrame(rows)


def series_features(days, amounts) -> dict:
    days, amounts = np.asarray(days, float), np.asarray(amounts, float)
    gaps = np.diff(days) if len(days) > 1 else np.array([0.0])
    mean_gap = float(gaps.mean()) if len(gaps) else 0.0
    nearest = min([7, 14, 30, 91, 365], key=lambda p: abs(p - mean_gap)) if mean_gap else 30
    return {
        "n": len(days),
        "mean_gap": mean_gap,
        "gap_cv": float(gaps.std() / mean_gap) if mean_gap > 0 else 9.0,
        "amount_cv": float(amounts.std() / amounts.mean()) if amounts.mean() > 0 else 9.0,
        "period_fit": float(abs(mean_gap - nearest) / nearest),
    }


# ------------------------------------------------------------------- cash flow
def make_daily_spend(n_users: int = 80, days: int = 180, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 4)
    rows = []
    for u in range(n_users):
        level = rng.lognormal(np.log(35), 0.5)
        weekly = rng.uniform(0.7, 1.4, 7)
        for d in range(days):
            spend = max(0.0, rng.gamma(2.0, level * weekly[d % 7] / 2.0) * (1.3 if d % 30 < 3 else 1.0))
            if rng.random() < 0.01:  # occasional big one-off (repair, gift, travel)
                spend += rng.lognormal(np.log(level * 8), 0.5)
            rows.append({"user": f"c{u:03d}", "day": d, "weekday": d % 7, "spend": round(spend, 2)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------- router intents
INTENT_EXAMPLES = {
    "refund": ["{item} not working since it came, need help", "got a defective {item}, what can i do", "{item} has a crack", "wrong size {item}, want to send it back", "{item} came broken pls help", "return pickup for {item}", "can I return my {item}", "my {item} stopped working can I get a refund",
               "I want my money back for the {item}", "is the {item} still returnable",
               "how do I get a replacement for my {item}", "refund status for my order",
               "the {item} arrived damaged", "return window for {item}", "{item} is broken what now",
               "send back the {item}", "the {item} doesn't work anymore", "exchange my {item}",
               "got a faulty {item}", "need to return something I bought", "where is my refund",
               "the {item} I ordered is defective", "can I still send this {item} back",
               "item not as described, want refund", "want a replacement for the dead {item}",
               "how many days do I have to return the {item}"],
    "payment_status": ["amount debited but order failed", "seller saying money not reached", "is my payment done or not", "transaction stuck in processing", "money cut from account but no confirmation", "did the vendor get my payment", "did my payment go through", "why does my supplier say payment wasn't received",
                       "was I charged twice", "payment failed what happened", "is my order paid",
                       "the app crashed while paying did it charge me", "check status of my last payment",
                       "supplier says unpaid", "did the money reach the seller", "I see two charges",
                       "my payment is stuck", "vendor claims they never got the money",
                       "was the payment successful", "internet dropped during checkout am I charged",
                       "confirm the supplier was paid", "payment pending for days",
                       "seller says not paid but I paid", "why is my payment on hold",
                       "did paypal take the money", "transaction status please"],
    "policy": ["what's the exchange policy", "can i open the box and still return", "do they give warranty on {item}", "return rules for this website", "any charges if i return", "terms and conditions for returns", "what is the return policy here", "explain the warranty for this {item}",
               "can I return this if I don't like it", "what are the refund terms",
               "is this product non returnable", "summarize the store policy", "what does the warranty cover",
               "how long is the return period", "who pays for return shipping", "is there a restocking fee",
               "explain the terms before I buy", "does this store accept returns",
               "what are the conditions to return", "fine print on this {item}",
               "replacement rules for this shop", "is the {item} covered by warranty",
               "read me the return rules", "any exclusions in the policy", "returns allowed after opening?",
               "what happens if the {item} is defective"],
    "budget": ["how much did i spend on food", "will i manage till salary", "can i buy {item} this month or not", "my expenses this month", "am i spending too much", "money left after bills", "can I afford this {item}", "how much budget do I have left", "am I overspending this month",
               "should I buy the {item} now or wait", "what bills are coming up",
               "show my spending by category", "will I have enough money for rent", "set a budget for dining",
               "how much did I spend this month", "am I on track this month", "what's left to spend",
               "can I buy the {item} without going broke", "is it ok to spend {amount} today",
               "what payments are due before payday", "where is my money going",
               "do I have money for the {item}", "how much can I spend this week",
               "upcoming bills", "monthly spending summary", "will this purchase hurt my budget"],
    "invoice": ["bill from vendor is higher than order", "check vendor bill", "supplier added extra charges", "invoice quantity doesn't match", "compare quote with final bill", "revised invoice from supplier", "check this invoice against the purchase order", "the supplier invoice looks higher than agreed",
                "verify invoice before paying", "invoice amount mismatch", "pay supplier invoice",
                "is this invoice correct", "compare the bill with what we ordered", "supplier billed extra",
                "invoice has items we didn't order", "quantity on the invoice is wrong",
                "check PO against bill", "validate the vendor invoice", "they charged more than quoted",
                "unit price on invoice differs", "review this bill before I approve",
                "is the supplier overcharging", "match invoice to order", "invoice total seems off",
                "approve invoice payment", "check the vendor bill"],
    "fraud": ["someone asking for otp", "link asking me to pay to unlock account", "unknown charge on my account", "they want me to pay to a different account", "fake looking payment request", "call from bank asking for details", "is this payment request a scam", "supplier changed bank details is that safe",
              "someone logged in from another country", "this invoice says urgent wire now",
              "check if this transaction is suspicious", "I got an email asking to pay immediately",
              "is this seller legit", "weird login on my account", "they want payment to a new account",
              "message says my account will be suspended", "could this be phishing",
              "strange charge I don't recognise", "someone is pressuring me to pay today",
              "new bank account on the invoice", "is this request fake", "I think I'm being scammed",
              "verify this payment request", "unknown device used my account", "suspicious payee",
              "they asked me to keep the payment confidential"],
    "subscription": ["which services auto debit every month", "monthly app charges", "when will my plan renew", "list auto payments", "memberships i pay for", "free trial ending soon?", "what subscriptions do I have", "which subscriptions renew this week",
                     "find recurring payments", "cancel my streaming subscription reminder",
                     "how much do I spend on subscriptions", "list my monthly plans", "what auto-pays do I have",
                     "any renewals coming up", "which services charge me every month", "show recurring charges",
                     "am I paying for things I don't use", "when does netflix renew",
                     "total cost of my subscriptions", "find repeating payments", "my memberships",
                     "what gets billed automatically", "recurring bills list", "trial converting to paid?",
                     "monthly charges I signed up for", "show standing payments"],
    "investment": ["mutual fund or fd", "where to invest my savings", "what is sip", "how much to keep for emergencies", "is investing in gold good", "invest {amount} safely", "should I invest {amount} or keep it", "I have {amount} available should I invest",
                   "explain index funds", "how risky is investing in stocks", "build a savings plan for investing",
                   "what is diversification", "where should I put {amount}", "is it a good time to invest",
                   "how do mutual funds work", "should I save or invest my bonus", "grow my {amount}",
                   "what's a safe way to invest", "long term investing options", "fixed deposit or stocks",
                   "can I invest without risking rent money", "beginner investing advice",
                   "how much should I keep as emergency fund", "invest {amount} for 5 years",
                   "explain risk vs return", "should I buy shares"],
    "price": ["was {item} cheaper before", "is this price ok", "alert me when {item} gets cheaper", "real discount or not", "price trend for {item}", "wait for sale or buy now", "has the price of {item} dropped", "price history for {item}", "is this a good price",
              "tell me when the {item} gets cheaper", "lowest price seen for {item}", "is the {item} on sale",
              "was the {item} cheaper before", "track the price of this {item}", "should I wait for a discount",
              "price alert for {item}", "is this the best deal", "did the {item} go down in price",
              "compare the price over time", "notify me on price drop", "cheapest the {item} has been",
              "is now a good time to buy the {item}", "price trend", "watch this item's price",
              "has it been cheaper", "deal check on {item}"],
    "cases": ["my recent purchases", "pending orders", "show my bills and receipts", "what's going on with my orders", "all my payments", "things that need action", "show my purchases", "what happened with my {item} order", "list my transactions",
              "show the briefcase for my last order", "what is still open", "my recent orders",
              "what did I buy last week", "show order history", "open cases", "anything pending",
              "where's my order record", "show everything about my {item} purchase", "what needs my attention",
              "list open issues", "my payment history", "show receipts", "recent activity",
              "what's happening with my orders", "show all my cases", "order details for the {item}"],
}
ITEMS = ["headphones", "laptop", "shoes", "phone", "jacket", "monitor", "keyboard", "camera", "earbuds",
         "speaker", "watch", "tablet", "charger", "mixer", "chair"]
AMOUNTS = ["$500", "500 dollars", "₹20,000", "$2000", "my bonus"]


def make_router_data(seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 5)
    rows = []
    for intent, templates in INTENT_EXAMPLES.items():
        for t in templates:
            for _ in range(10):
                text = t.format(item=rng.choice(ITEMS), amount=rng.choice(AMOUNTS))
                if rng.random() < 0.1:  # typos happen
                    i = int(rng.integers(1, max(2, len(text) - 1)))
                    text = text[:i] + text[i + 1:]
                if rng.random() < 0.3:
                    text = text.capitalize() + rng.choice(["?", "", " please", " asap"])
                if rng.random() < 0.15:
                    text = rng.choice(["hey ", "hi, ", "quick question: "]) + text
                rows.append({"text": text, "intent": intent, "template": t})
    return pd.DataFrame(rows).drop_duplicates(subset=["text"]).reset_index(drop=True)
