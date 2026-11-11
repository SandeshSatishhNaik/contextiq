import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.agents import commerce
from app.intelligence import decision
from app.ml import runtime

print("=" * 70)
print("1. INTENT ROUTER SPECIALIST MODEL")
print("=" * 70)
queries = [
    "Can I return the headphones I bought last week?",
    "Did my payment to Nova Parts go through?",
    "What is my dining spending this month?",
    "I see an unauthorized charge on my account",
    "Cancel my StreamFlix subscription",
    "Should I invest my spare cash?",
    "Check invoice for sensor boards against PO-1041"
]
for q in queries:
    intent, conf = runtime.route_intent(q)
    print(f"  Query: '{q}'\n    -> Intent: {intent} (Confidence: {conf:.1%})")

print("\n" + "=" * 70)
print("2. TRANSACTION PURPOSE & SPENDING CATEGORY CLASSIFIERS")
print("=" * 70)
txs = [
    ("FreshMart", "weekly groceries store", "online", 14, 2, 85.50, True),
    ("Nova Parts Co", "batch invoice sensor boards", "invoice", 11, 1, 1250.00, True),
    ("Steam Games", "digital game purchase", "online", 22, 5, 49.99, False),
    ("QuickCab", "taxi ride downtown", "pos", 19, 4, 18.25, False),
    ("CloudHost", "server hosting subscription", "online", 3, 0, 29.00, True)
]
for payee, desc, ch, hr, wd, amt, biz in txs:
    res = runtime.classify_transaction(payee, desc, ch, hr, wd, amt, biz)
    print(f"  Tx: {payee} (${amt:,.2f}) [{desc}]\n    -> Purpose: {res['purpose'].upper()} ({res['purpose_confidence']:.1%}) | Category: {res['category'].upper()} ({res['category_confidence']:.1%})")

print("\n" + "=" * 70)
print("3. MULTI-LAYER FRAUD & ANOMALY DETECTION ENGINE")
print("=" * 70)
scenarios = [
    ("Legitimate Shopper Payment", {"amount_z": 0.2, "log_amount": 3.5, "session_age_min": 45}),
    ("Account Takeover (New Device + IP Mismatch + Burst)", {
        "new_device": 1, "ip_country_mismatch": 1, "unusual_hour": 1, "new_payee": 1,
        "amount_z": 2.8, "burst_1h": 3, "session_age_min": 2
    }),
    ("Invoice Inflation (> PO agreed price)", {
        "invoice_po_ratio": 1.45, "amount_z": 1.2
    }),
    ("Urgent Impersonation Wire Request", {
        "urgency_score": 0.85, "new_payee": 1, "payee_changed_recently": 1, "amount_z": 3.5
    })
]
for name, feats in scenarios:
    res = runtime.fraud_score(feats)
    print(f"  Scenario: {name}\n    -> Gateway Verdict: {res['decision'].upper()} (Risk Score: {res['score']})\n    -> Layers Triggered: {res['layers_fired']}\n    -> Specific Reasons: {res['reasons']}")

print("\n" + "=" * 70)
print("4. SUBSCRIPTION RECURRING DETECTION MODEL")
print("=" * 70)
sub_days = [1.0, 31.0, 61.0, 92.0]
sub_amts = [15.99, 15.99, 15.99, 15.99]
is_sub, conf = runtime.is_subscription(sub_days, sub_amts)
print(f"  Series: StreamFlix ($15.99 monthly on day 1)\n    -> Is Subscription: {is_sub} (Confidence: {conf:.1%})")

erratic_days = [2.0, 5.0, 19.0, 27.0]
erratic_amts = [22.50, 48.00, 12.00, 75.30]
is_sub2, conf2 = runtime.is_subscription(erratic_days, erratic_amts)
print(f"  Series: Dining Out (random intervals & amounts)\n    -> Is Subscription: {is_sub2} (Confidence: {conf2:.1%})")

print("\n" + "=" * 70)
print("5. DECISION OPTIMIZATION ENGINE (Policy & Consumer Rights)")
print("=" * 70)
windows = {
    "return_window": {"status": "open"},
    "replacement_window": {"status": "open"},
    "warranty": {"status": "open"}
}
opts = commerce.build_refund_options(windows, defect=True, evidence_conf=0.95, captured=True, best="replacement_window", prefers_refund=False)
weights = json.loads(open(os.path.join(os.path.dirname(__file__), "../app/ml/models/decision_weights.json")).read())["weights"]
chosen = decision.decide(opts, weights)
print(f"  Defective Headphones Scenario:\n    -> Optimal Action: {chosen['choice']['name']}\n    -> Score: {chosen['choice']['score']:.3f}\n    -> Explanation: {chosen['choice']['explanation']}")

print("\n" + "=" * 70)
print("6. CASH FLOW FORECASTER")
print("=" * 70)
fc = runtime.forecaster()
print(f"  Forecaster profile: {fc.profile}, shrinkage factor: {fc.shrink}")
print("  Successfully loaded and validated forecaster artifact.")
