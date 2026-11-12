import os
import tempfile
from pathlib import Path

_test_db = Path(tempfile.gettempdir()) / "ciq_test.db"
os.environ["PAYPAL_ENV"] = "mock"
os.environ["VOICE_TOKEN"] = ""  # keep the voice endpoint open in tests even if .env sets a token
for _k in ("GROQ_API_KEY", "ANTHROPIC_API_KEY"):  # no live LLM in tests: deterministic wording, no key spend
    os.environ[_k] = ""
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.as_posix()}"
if _test_db.exists():
    try:
        _test_db.unlink()
    except Exception:
        pass

from datetime import UTC

from fastapi.testclient import TestClient

from app.main import app
from app.seed import DEMO_POLICY

H = {"X-User-Id": "alex"}
CART = {"merchant": "BrightMart Electronics", "seller_id": "brightmart", "currency": "USD",
        "items": [{"name": "SoundWave Headphones", "unit_price": 249.0}], "policy_text": DEMO_POLICY,
        "policy_url": "http://localhost:8000/demo-store/policy.html"}


def client():
    c = TestClient(app)
    c.__enter__()
    return c


c = client()


def _pay(drop=False):
    co = c.post("/api/checkout", json=CART, headers=H).json()
    cid, tok = co["case_id"], co["approval_token"]
    c.post(f"/api/cases/{cid}/approve-mock")
    url = f"/api/cases/{cid}/simulate-drop" if drop else f"/api/cases/{cid}/capture"
    r = c.post(url, json={"approval_token": tok}, headers=H).json()
    if r.get("gateway") == "step_up":
        r = c.post(url, json={"approval_token": tok, "step_up_code": r["step_up_code_demo"]}, headers=H).json()
    return cid, tok, r


def test_cart_analysis():
    r = c.post("/api/cart/analyze", json=CART, headers=H).json()
    assert r["policy"]["terms"]["return_window_days"] == 30
    assert r["policy"]["terms"]["starts_from"] == "delivery"
    assert r["policy"]["terms"]["warranty_days"] == 365
    assert r["budget"]["verdict"] in ("ok", "wait")


def test_gateway_denies_without_approval():
    co = c.post("/api/checkout", json=CART, headers=H).json()
    c.post(f"/api/cases/{co['case_id']}/approve-mock")
    r = c.post(f"/api/cases/{co['case_id']}/capture", json={"approval_token": "forged"}, headers=H).json()
    assert r["ok"] is False and r["gateway"] == "deny"


def test_step_up_then_capture():
    cid, tok, r = _pay()
    assert r["ok"] and r["capture_id"]
    v = c.get(f"/api/cases/{cid}", headers=H).json()
    assert v["case"]["payment_state"] == "captured"
    assert any(e["provenance"] == "verified" and e["kind"] == "paypal_capture" for e in v["evidence"])
    # approval cannot be reused
    r2 = c.post(f"/api/cases/{cid}/capture", json={"approval_token": tok}, headers=H).json()
    assert r2["ok"] is False


def test_self_healing_no_double_charge():
    cid, tok, r = _pay(drop=True)
    assert r["ok"] and r["healed"]
    assert r["paypal_captures_for_order"] == 1
    assert any("no second charge" in t for t in r["trace"])


def test_webhook_dedupe():
    r = c.post("/api/mock/deliver-webhooks").json()
    assert r["duplicates_dropped"] >= 1


def test_refund_flow():
    cid, tok, r = _pay()
    c.post(f"/api/cases/{cid}/delivered?days_ago=2")
    el = c.get(f"/api/cases/{cid}/refund-eligibility", params={"issue": "stopped working"}, headers=H).json()
    assert el["eligible"] and el["basis"] == "replacement_window"
    chat = c.post("/api/chat", json={"message": "My headphones stopped working, can I get a refund?"}, headers=H).json()
    assert chat["intent"] == "refund"
    S = {"X-User-Id": "brightmart"}
    at = c.post(f"/api/cases/{cid}/refund/approve", headers=S).json()["approval_token"]
    rf = c.post(f"/api/cases/{cid}/refund", json={"approval_token": at, "reason": "defective"}, headers=S).json()
    if rf.get("gateway") == "step_up":
        rf = c.post(f"/api/cases/{cid}/refund", json={"approval_token": at, "step_up_code": rf["step_up_code_demo"]}, headers=S).json()
    assert rf["ok"], rf
    assert c.get(f"/api/cases/{cid}", headers=H).json()["case"]["payment_state"] == "refunded"


def test_buyer_cannot_refund_and_seller_view_is_scoped():
    cid, tok, r = _pay()
    rf = c.post(f"/api/cases/{cid}/refund", json={"approval_token": "x"}, headers=H).json()
    assert rf["ok"] is False
    sv = c.get(f"/api/cases/{cid}", headers={"X-User-Id": "brightmart"}).json()
    assert sv["role"] == "seller"
    assert all(e["kind"] != "classification" for e in sv["evidence"])  # buyer-only evidence hidden
    assert c.get(f"/api/cases/{cid}", headers={"X-User-Id": "novaparts"}).status_code == 404


def test_payment_investigation():
    cid, tok, r = _pay()
    out = c.post(f"/api/cases/{cid}/investigate", headers=H).json()
    assert out["verdict"] == "paid"


def test_qr_signed_and_replay_blocked():
    q = c.post("/api/qr/create", json={"items": [{"name": "USB-C cable", "unit_price": 12.5, "quantity": 2}]},
               headers={"X-User-Id": "brightmart"}).json()
    s1 = c.post("/api/qr/scan", json={"token": q["qr_token"]}, headers=H).json()
    assert s1["ok"] and s1["verified_merchant"] == "BrightMart Electronics"
    s2 = c.post("/api/qr/scan", json={"token": q["qr_token"]}, headers=H).json()
    assert not s2["ok"] and "replay" in s2["error"]
    tampered = q["qr_token"][:-3] + ("AAA" if not q["qr_token"].endswith("AAA") else "BBB")
    assert not c.post("/api/qr/scan", json={"token": tampered}, headers=H).json()["ok"]


def test_invoice_mismatch():
    po = {"payee": "Nova Parts Co", "items": [{"name": "Sensor board", "unit_price": 40, "quantity": 30}]}
    inv = {"payee": "Nova Parts Co", "items": [{"name": "Sensor board", "unit_price": 42.5, "quantity": 30}]}
    r = c.post("/api/invoice/check", json={"supplier": "Nova Parts Co", "po": po, "invoice": inv}, headers=H).json()
    assert r["status"] == "mismatch" and r["difference"] == 75.0


def test_chat_intents():
    for msg, intent in [("what subscriptions do I have", "subscription"), ("can I afford $300 headphones", "budget"),
                        ("I have $1000, should I invest it?", "investment"), ("show my purchases", "cases"),
                        ("supplier changed bank details, urgent wire now", "fraud")]:
        r = c.post("/api/chat", json={"message": msg}, headers=H).json()
        assert r["intent"] == intent, (msg, r["intent"])


def test_home_and_metrics():
    assert len(c.get("/api/home", headers=H).json()["shortcuts"]) >= 5
    m = c.get("/api/metrics").json()
    assert "fraud" in m["models"]


def test_account_memory_stops_asking():
    r = c.post("/api/accounts/classify", json={"payee": "Nova Parts Co", "amount": 950, "description": "sensor boards"}, headers=H).json()
    assert not r["needs_confirmation"] and r["low_confidence"]  # large amount → filed automatically, change link highlighted
    c.post("/api/accounts/remember", json={"payee": "Nova Parts Co", "purpose": "business"}, headers=H)
    r2 = c.post("/api/accounts/classify", json={"payee": "Nova Parts Co", "amount": 950}, headers=H).json()
    assert r2["purpose"] == "business" and not r2["needs_confirmation"]


def test_qr_formats():
    q = lambda raw: c.post("/api/qr/interpret", json={"raw": raw}, headers=H).json()
    upi = q("upi://pay?pa=shop@okbank&pn=Shop&am=450.00&cu=INR")
    assert upi["format"] == "UPI payment request" and upi["amount"] == 450.0 and not upi["payable_with_paypal"]
    emv = q("000201010212" + "5303356" + "5406450.00" + "5802IN" + "5904Shop" + "6009Bengaluru")
    assert emv["format"] == "EMVCo merchant QR" and emv["payee"] == "Shop" and emv["amount"] == 450.0
    assert q("https://paypal.me/someshop/25")["payable_with_paypal"]


def test_two_sided_claims_and_checklist():
    cid, tok, r = _pay()
    c.post(f"/api/cases/{cid}/claims", json={"topic": "delivered", "value": False}, headers=H)
    c.post(f"/api/cases/{cid}/claims", json={"topic": "delivered", "value": True}, headers={"X-User-Id": "brightmart"})
    cmp_ = c.get(f"/api/cases/{cid}/compare", headers=H).json()
    d = next(p for p in cmp_["points"] if p["topic"] == "delivered")
    assert d["status"] == "disputed"
    v = c.get(f"/api/cases/{cid}", headers=H).json()
    assert any(i["item"] == "Payment captured by PayPal" and i["done"] for i in v["checklist"])


def test_voice_never_moves_money():
    r = c.post("/api/voice", json={"text": "pay my supplier 500 dollars"}, headers=H).json()
    assert r.get("blocked_action")
    r2 = c.post("/api/voice", json={"text": "what subscriptions do I have"}, headers=H).json()
    assert "recurring" in r2["speech"].lower()


def test_non_defect_cannot_use_replacement_window():
    cid, tok, r = _pay()
    c.post(f"/api/cases/{cid}/delivered?days_ago=2")
    el = c.get(f"/api/cases/{cid}/refund-eligibility", params={"issue": "I just don't like the colour"}, headers=H).json()
    assert el["basis"] == "return_window"


def test_decision_model_order_invariant():
    from app.intelligence.decision import Option, benchmark_order_invariance
    opts = [Option("a", {"benefit": 0.5}), Option("b", {"benefit": 0.7, "risk": 0.2}), Option("c", {"benefit": 0.6})]
    assert benchmark_order_invariance(opts) == 1.0


def test_a2a_handshake_privacy_tamper_replay_and_sync():
    from app.db import SessionLocal
    cid, tok, r = _pay()
    s = c.post("/api/a2a/sessions", json={"case_id": cid}, headers=H).json()
    assert s["ok"] and s["comparison"]["match"]
    assert all(t["verified"] for t in s["transcript"])
    assert "monthly_budget_left" not in s["shared_by_buyer"] and "other_purchases" not in s["shared_by_buyer"]
    bad = c.post("/api/a2a/sessions", json={"case_id": cid, "tamper": "change_amount"}, headers=H).json()
    assert not bad["ok"] and any(t["rejected_because"] for t in bad["transcript"])
    # replay: deliver an already-accepted envelope again
    db = SessionLocal()
    from app.models import A2AMessage
    msg = db.query(A2AMessage).filter(A2AMessage.verified.is_(True)).first()
    rep = c.post("/a2a/inbox", json=msg.envelope).json()
    assert not rep["accepted"] and ("replay" in rep["reason"] or "stale" in rep["reason"])
    db.close()
    f = c.post(f"/api/a2a/sessions/{s['session']}/sync?simulate_failure=true", headers=H).json()
    assert f["sync_state"] == "sync_failed_will_retry" and f["payment_state"] == "captured"
    ok = c.post(f"/api/a2a/sessions/{s['session']}/sync", headers=H).json()
    assert ok["sync_state"] == "synced"


def test_a2a_revoked_key_rejected():
    cid, tok, r = _pay()
    s = c.post("/api/a2a/sessions", json={"case_id": cid}, headers=H).json()
    from app.db import SessionLocal
    from app.models import A2AMessage
    db = SessionLocal()
    old = db.query(A2AMessage).filter(A2AMessage.session_id == s["session"], A2AMessage.sender.like("agent:seller:%")).first().envelope
    db.close()
    c.post("/api/a2a/rotate", headers={"X-User-Id": "brightmart"})
    old2 = dict(old, nonce="fresh-nonce-123")
    rep = c.post("/a2a/inbox", json=old2).json()
    assert not rep["accepted"] and "revoked" in rep["reason"]  # card check runs before the signature check


def test_temporal_graph_as_of_contradictions_and_scoping():
    from datetime import datetime
    cid, tok, r = _pay()
    before = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
    assert c.get("/api/kg/as-of", params={"case_id": cid, "at": before}, headers=H).json()["facts"] == []
    now_facts = c.get("/api/kg/as-of", params={"case_id": cid, "at": datetime.now(UTC).isoformat()}, headers=H).json()["facts"]
    assert any(f["relation"] == "payment status" and f["object"] == "paid" for f in now_facts)
    c.post(f"/api/cases/{cid}/claims", json={"topic": "paid", "value": False}, headers={"X-User-Id": "brightmart"})
    con = c.get("/api/kg/contradictions", headers=H).json()
    assert any("verified" in x["trust"] and x["about"] == "payment_status" for x in con)
    hits = c.get("/api/kg/retrieve", params={"q": "SoundWave headphones"}, headers={"X-User-Id": "novaparts"}).json()
    assert not any("SoundWave" in f["subject"] or "SoundWave" in f["object"] for f in hits["facts"])  # not novaparts' data


def test_market_research_and_diversification():
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from fixtures.alphavantage import transport

    from app.market.provider import MarketData, diversification, research
    assert research("ACME", MarketData(api_key="", transport=transport()))["connected"] is False
    r = research("ACME", MarketData(api_key="test", transport=transport()))
    assert r["quote"]["price"] == 123.45 and r["fundamentals"]["sector"] == "TECHNOLOGY"
    assert any("beta" in x for x in r["risk_flags"]) and any("negative" in x for x in r["risk_flags"])
    d = diversification([{"symbol": "ACME", "value": 7000, "sector": "TECH"}, {"symbol": "IDX", "value": 3000, "sector": "INDEX"}])
    assert d["level"] == "concentrated" and d["notes"]


def test_plugin_registry_and_mcp_tools():
    import asyncio

    from app import plugins
    from app.mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_purchases", "check_refund_eligibility", "budget_status", "ask"} <= names
    assert not any(n in names for n in ("capture", "refund", "pay", "issue_refund"))  # no money tools for AI
    reg = {p["id"]: p for p in c.get("/api/plugins").json()}
    assert reg["paypal.rest"]["callable_by_ai"] is False
    import pytest
    with pytest.raises(plugins.PermissionDenied):
        plugins.call("paypal.rest", "captures", "alex", {}, lambda: None)
    with pytest.raises(plugins.PermissionDenied):
        plugins.call("contextiq.budget", "budget_status", "alex", {}, lambda: 1, grants={"chat"})
    p = plugins.REGISTRY["alphavantage.market"]
    with pytest.raises(plugins.RateLimited):
        for _ in range(p.rate_limit_per_min + 1):
            plugins.call("alphavantage.market", "quote", "ratetest", {"symbol": "X"}, lambda symbol: 1)
    out = plugins.call("contextiq.cases", "list_purchases", "alex", {}, lambda: ["ok"])
    assert out == ["ok"]


def test_passkey_api_rejects_bad_credentials():
    assert c.get("/api/passkeys/status", headers=H).json()["has_passkey"] in (False, True)
    opts = c.post("/api/passkeys/register/options", headers=H).json()
    assert opts["rp"]["id"] == "localhost" and opts["challenge"]
    bad = c.post("/api/passkeys/register/verify", json={"id": "x", "rawId": "x", "type": "public-key",
                                                         "response": {"clientDataJSON": "e30", "attestationObject": "AA"}}, headers=H)
    assert bad.status_code == 400


def test_insights_tell_without_asking():
    r = c.get("/api/insights?hour=20&weekday=1").json()
    kinds = {c["kind"] for c in r["cards"]}
    assert r["context"]["account"] == "personal"
    assert "deadline" in kinds and "price_drop" in kinds  # closing window + cart price drop surfaced unprompted
    drop = next(c for c in r["cards"] if c["kind"] == "price_drop")
    assert drop["numbers"]["now"] < drop["numbers"]["before"]
    biz = c.get("/api/insights?hour=10&weekday=1").json()
    assert biz["context"]["account"] == "business" and any(c["kind"] == "supplier" for c in biz["cards"])
    assert c.get("/api/insights?hour=10&weekday=1&account=personal").json()["context"]["account"] == "personal"


def test_setup_and_travel_mode():
    assert c.post("/api/profile/setup", json={"uses": "both", "goals": ["deals"], "location_ok": True,
                                                   "home_lat": 12.97, "home_lon": 77.59, "monthly_budget": 1900}).json()["ok"]
    r = c.get("/api/insights?hour=20&weekday=1&lat=19.07&lon=72.87").json()  # Mumbai, ~850 km away
    assert r["context"]["travel"] and any(x["kind"] == "travel" for x in r["cards"])
    assert c.get("/api/profile").json()["setup_done"]


def test_chat_is_conversational_and_specific():
    r = c.post("/api/chat", json={"message": "hello"}).json()
    assert r["answer"].startswith("Hi") and r["suggestions"]
    a = c.post("/api/chat", json={"message": "can i afford the earbuds"}).json()
    assert "earbuds" in a["answer"].lower() and a.get("action", {}).get("cart_item")
    f = c.post("/api/chat", json={"message": "did the price drop?"}).json()  # follow-up resolves to the earbuds
    assert "earbuds" in f["answer"].lower()
    again = c.post("/api/chat", json={"message": "can i afford the earbuds"}).json()
    assert again["answer"] != a["answer"]  # never repeats word for word


def test_bills_pay_and_recommendations():
    bills = c.get("/api/bills").json()
    bill = next(b for b in bills if b["kind"] == "bill")
    co = c.post(f"/api/bills/{bill['id']}/checkout").json()
    c.post(f"/api/cases/{co['case_id']}/approve-mock")
    r = c.post(f"/api/cases/{co['case_id']}/capture", json={"approval_token": co["approval_token"]}).json()
    if r.get("gateway") == "step_up":  # the security gateway may ask to confirm it's you — that's expected
        r = c.post(f"/api/cases/{co['case_id']}/capture", json={"approval_token": co["approval_token"],
                                                               "step_up_code": r["step_up_code_demo"]}).json()
    assert r["ok"], r
    assert bill["id"] not in {b["id"] for b in c.get("/api/bills").json()}
    recs = c.get("/api/recommendations").json()
    assert recs["items"] and all(r["title"] and r["body"] for r in recs["items"])


def test_paypal_return_cannot_inject_script():
    html = c.get("/checkout/return", params={"case": "x';alert(1);//"}).text
    assert "alert" not in html and "/?approved=" in html
    assert '"/?approved=abc123"' in c.get("/checkout/return", params={"case": "abc123"}).text


def test_reset_needs_mock_mode_or_admin_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "paypal_env", "sandbox")
    monkeypatch.setattr(settings, "admin_token", "")
    assert c.post("/api/reset").status_code == 403
    monkeypatch.setattr(settings, "admin_token", "t0ken")
    assert c.post("/api/reset", headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_non_participant_cannot_act_on_case():
    cid, tok, r = _pay()
    stranger = {"X-User-Id": "novaparts"}
    assert c.post(f"/api/cases/{cid}/resolution", json={"action": "request_swap"}, headers=stranger).status_code == 404
    assert c.get(f"/api/cases/{cid}/refund-eligibility", headers=stranger).status_code == 404
    assert c.post(f"/api/cases/{cid}/investigate", headers=stranger).status_code == 404
    assert c.post(f"/api/cases/{cid}/refund/approve", headers=stranger).status_code == 404


def test_seller_ships_with_paypal_tracking():
    cid, tok, r = _pay()
    assert c.post(f"/api/cases/{cid}/ship", json={}, headers=H).status_code == 403  # buyer can't
    s = c.post(f"/api/cases/{cid}/ship", json={"tracking_number": "1Z999AA10123456784", "carrier": "ups"},
               headers={"X-User-Id": "brightmart"}).json()
    assert s["ok"] and s["carrier"] == "UPS"
    v = c.get(f"/api/cases/{cid}", headers=H).json()
    assert any(e["kind"] == "paypal_tracking" and e["provenance"] == "verified" for e in v["evidence"])
    assert any(i["item"].startswith("Shipped") and i["done"] for i in v["checklist"])


def test_paypal_dispute_fought_with_briefcase_evidence():
    S = {"X-User-Id": "brightmart"}
    cid, tok, r = _pay()
    c.post(f"/api/cases/{cid}/ship", json={"tracking_number": "9400111899223344556677"}, headers=S)
    c.post(f"/api/mock/open-dispute/{cid}", headers=H)  # buyer files "item not received" at PayPal
    assert c.post(f"/api/cases/{cid}/dispute/draft", headers=H).status_code == 403  # buyer can't answer
    dr = c.post(f"/api/cases/{cid}/dispute/draft", headers=S).json()
    assert dr["recommendation"] == "fight"
    ev = dr["payload"]["evidences"][0]
    assert ev["evidence_type"] == "PROOF_OF_FULFILLMENT"
    assert ev["evidence_info"]["tracking_info"][0]["tracking_number"] == "9400111899223344556677"
    assert not c.post(f"/api/cases/{cid}/dispute/submit", json={"draft_hash": "tampered"}, headers=S).json()["ok"]
    sub = c.post(f"/api/cases/{cid}/dispute/submit", json={"draft_hash": dr["draft_hash"]}, headers=S).json()
    assert sub["ok"], sub
    dec = c.post(f"/api/cases/{cid}/dispute/sandbox-decide", json={}, headers=S).json()
    assert dec["outcome"] == "RESOLVED_SELLER_FAVOUR", dec
    assert c.get(f"/api/cases/{cid}/dispute", headers=H).json()["dispute"]["status"] == "RESOLVED"


def test_paypal_dispute_accepted_goes_through_gateway():
    S = {"X-User-Id": "brightmart"}
    cid, tok, r = _pay()
    c.post(f"/api/mock/open-dispute/{cid}", headers=H)  # no tracking on file
    assert c.post(f"/api/cases/{cid}/dispute/draft", headers=S).json()["recommendation"] == "accept"
    assert not c.post(f"/api/cases/{cid}/dispute/accept", json={"approval_token": "forged"}, headers=S).json()["ok"]
    at = c.post(f"/api/cases/{cid}/refund/approve", headers=S).json()["approval_token"]
    a = c.post(f"/api/cases/{cid}/dispute/accept", json={"approval_token": at}, headers=S).json()
    if a.get("gateway") == "step_up":
        a = c.post(f"/api/cases/{cid}/dispute/accept", json={"approval_token": at, "step_up_code": a["step_up_code_demo"]},
                   headers=S).json()
    assert a["ok"], a
    assert c.get(f"/api/cases/{cid}", headers=H).json()["case"]["payment_state"] == "refunded"


def test_dispute_under_review_gets_supporting_info():
    """A case already in PayPal review only accepts supporting info; the agent follows PayPal's links."""
    from app.agents import dispute_response
    from app.db import SessionLocal
    from app.models import Case
    from app.paypal import mock

    S = {"X-User-Id": "brightmart"}
    cid, tok, r = _pay()
    c.post(f"/api/cases/{cid}/ship", json={"tracking_number": "9400111899223344550000"}, headers=S)
    with SessionLocal() as db:
        case = db.get(Case, cid)
        d = mock.open_dispute(case.paypal_capture_id, status="UNDER_REVIEW")
        dispute_response.record(db, d)
        db.commit()
    dr = c.post(f"/api/cases/{cid}/dispute/draft", headers=S).json()
    sub = c.post(f"/api/cases/{cid}/dispute/submit", json={"draft_hash": dr["draft_hash"]}, headers=S).json()
    assert sub["ok"] and sub["via"] == "provide-supporting-info", sub
    assert "9400111899223344550000" in mock.DISPUTES[d["dispute_id"]]["supporting_info"][0]["notes"]



def test_signed_mandate_on_order_and_enforced_at_capture():
    from app.db import SessionLocal
    from app.models import Case
    from app.paypal import mock
    from app.security import mandate

    co = c.post("/api/checkout", json=CART, headers=H).json()
    cid = co["case_id"]
    m = c.get(f"/api/cases/{cid}/mandate", headers=H).json()
    assert m["valid"] and m["mandate"]["max_amount"] == 249.0 and "token" not in m["mandate"]
    unit = mock.ORDERS[co["order"]["order_id"]]["purchase_units"][0]
    assert unit["custom_id"] == f"ciqm:{m['mandate']['hash']}"  # PayPal's record points back to the mandate
    with SessionLocal() as db:
        case = db.get(Case, cid)
        assert not mandate.verify(db, case, amount=500.0)[0]                       # over the cap
        assert not mandate.verify(db, case, payee="Somebody Else")[0]              # different payee
        tok = mandate.current(db, case).content["token"]
        forged = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
        assert not mandate.verify(db, case, token=forged)[0]                      # altered signature
    t = c.post(f"/api/cases/{cid}/mandate/overspend-test", headers=H).json()
    assert t["blocked"] == 2
    assert c.post(f"/api/cases/{cid}/mandate/revoke", headers={"X-User-Id": "brightmart"}).status_code == 403
    assert c.post(f"/api/cases/{cid}/mandate/revoke", headers=H).json()["ok"]
    c.post(f"/api/cases/{cid}/approve-mock")
    r = c.post(f"/api/cases/{cid}/capture", json={"approval_token": co["approval_token"]}, headers=H).json()
    assert r["ok"] is False and "revoked" in r["reasons"][0]  # fails closed after revocation


def test_dispute_draft_cites_the_mandate():
    S = {"X-User-Id": "brightmart"}
    cid, tok, r = _pay()
    c.post(f"/api/mock/open-dispute/{cid}", headers=H)
    dr = c.post(f"/api/cases/{cid}/dispute/draft", headers=S).json()
    assert any("signed spending mandate" in f for f in dr["facts"])
    assert any(p["label"].startswith("Buyer's signed") and p["present"] for p in dr["proofs"])



def test_dispute_readiness_before_any_dispute():
    S = {"X-User-Id": "brightmart"}
    cid, tok, r = _pay()
    assert c.get(f"/api/cases/{cid}/dispute-readiness", headers=H).status_code == 403  # seller-only
    before = c.get(f"/api/cases/{cid}/dispute-readiness", headers=S).json()
    assert before["have"] == before["of"] - 1  # only tracking missing, with a fix suggested
    assert next(p for p in before["proofs"] if not p["present"])["fix"]
    c.post(f"/api/cases/{cid}/ship", json={}, headers=S)
    after = c.get(f"/api/cases/{cid}/dispute-readiness", headers=S).json()
    assert after["have"] == after["of"]



def test_payment_status_question_is_not_treated_as_cart_advice():
    r = c.post("/api/chat", json={"message": "did my payment to brightmart go through"}, headers=H).json()
    assert r["intent"] != "cart_item", r["intent"]


def test_category_keywords_and_confidence_gate():
    from app.ml import runtime as R

    assert R.classify_transaction("Uber", "ride home", "online", 23, 4, 38.0, False)["category"] == "transport"
    assert R.classify_transaction("Uber Eats", "dinner order", "online", 20, 4, 28.0, False)["category"] == "dining"
    assert R.classify_transaction("Pacific Gas & Electric", "electricity bill", "online", 9, 1, 142.0, False)["category"] == "utilities"
    unsure = R.classify_transaction("Etsy", "handmade gift", "online", 21, 4, 36.0, False)
    assert unsure["category"] == "uncategorized" and unsure["category_source"] == "unsure"  # no silent wrong label
