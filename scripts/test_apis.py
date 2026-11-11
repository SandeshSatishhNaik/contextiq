import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx

from app.config import settings

print("=" * 60)
print("TEST 1: GROQ LLM API & MODELS")
print("=" * 60)
from app.intelligence import llm

print(f"Provider: {llm.PROVIDER}")
print(f"Available: {llm.available()}")
print(f"Groq Key: {llm.GROQ_KEY[:6]}...{llm.GROQ_KEY[-4:] if llm.GROQ_KEY else ''}")

# Test Small Model
print(f"\n--> Testing Groq Small Model ({llm.GROQ_SMALL})...")
small_resp = llm.complete(
    system="You are ContextIQ assistant for PayPal hackathon.",
    user="Say: Groq Llama 3.1 8B is fully operational.",
    large=False
)
print("Response:", small_resp)

# Test Large Model
print(f"\n--> Testing Groq Large Model ({llm.GROQ_LARGE})...")
large_resp = llm.complete(
    system="You are ContextIQ assistant for PayPal hackathon.",
    user="Say: Groq Llama 3.3 70B is fully operational.",
    large=True
)
print("Response:", large_resp)

print("\n" + "=" * 60)
print("TEST 2: PAYPAL SANDBOX REST API")
print("=" * 60)
print(f"PayPal Env: {settings.paypal_env}")
print(f"Base URL: {settings.paypal_base_url}")
print(f"Client ID: {settings.paypal_client_id[:12]}...{settings.paypal_client_id[-8:]}")

token_res = httpx.post(
    f"{settings.paypal_base_url}/v1/oauth2/token",
    auth=(settings.paypal_client_id, settings.paypal_client_secret),
    data={"grant_type": "client_credentials"},
    timeout=15.0
)
print(f"OAuth status: {token_res.status_code}")
if token_res.status_code == 200:
    tok_data = token_res.json()
    access_token = tok_data.get("access_token")
    print("SUCCESS: Access token received!")
    print(f"App ID: {tok_data.get('app_id')}")
    print(f"Expires in: {tok_data.get('expires_in')} seconds")
    print(f"Scope: {tok_data.get('scope')[:80]}...")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "PayPal-Request-Id": f"test-ciq-{os.urandom(4).hex()}"
    }
    order_payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": "test-ref-001",
            "amount": {
                "currency_code": "USD",
                "value": "10.00"
            },
            "description": "ContextIQ Sandbox Connectivity Test"
        }],
        "application_context": {
            "return_url": "http://localhost:8000/paypal/return",
            "cancel_url": "http://localhost:8000/paypal/cancel"
        }
    }
    order_res = httpx.post(f"{settings.paypal_base_url}/v2/checkout/orders", headers=headers, json=order_payload, timeout=15.0)
    print(f"Order creation status: {order_res.status_code}")
    if order_res.status_code in (200, 201):
        order_data = order_res.json()
        print(f"SUCCESS: Order created! ID: {order_data.get('id')}, Status: {order_data.get('status')}")
        links = {link.get('rel'): link.get('href') for link in order_data.get('links', [])}
        print(f"Approve Link: {links.get('approve')}")
    else:
        print(f"Order creation response: {order_res.text}")
else:
    print(f"OAuth FAILED: {token_res.text}")

print("\n" + "=" * 60)
print("TEST 3: ALPHAVANTAGE MARKET DATA API")
print("=" * 60)
av_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
print(f"AlphaVantage Key: {av_key[:4]}...{av_key[-4:] if av_key else ''}")
av_res = httpx.get(
    f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=PYPL&apikey={av_key}",
    timeout=15.0
)
print(f"AlphaVantage HTTP status: {av_res.status_code}")
try:
    av_json = av_res.json()
    quote = av_json.get("Global Quote", {})
    if quote:
        print("SUCCESS: Live PYPL Quote fetched:")
        print(f"  Symbol: {quote.get('01. symbol')}")
        print(f"  Price: ${quote.get('05. price')}")
        print(f"  Change: {quote.get('09. change')} ({quote.get('10. change percent')})")
        print(f"  Latest Trading Day: {quote.get('07. latest trading day')}")
    else:
        print("Response body:", av_json)
except Exception as e:
    print(f"JSON decode error: {e}")

