# ContextIQ: the AI agent that keeps working after you pay

> Every PayPal payment gets an evidence briefcase. When a buyer opens a PayPal dispute, ContextIQ answers it from that briefcase, and a person approves before anything is sent.

**Try it:** https://contextiq-0ihy.onrender.com/?demo=1 (guided judge tour; free hosting, so the first load can take about a minute) · **Code:** https://github.com/SandeshSatishhNaik/contextiq (Apache-2.0) · **Team:** Avoflare

---

## Inspiration

Checkout knows a card and an amount. It forgets everything else the moment the payment completes: what the store promised, what exactly the buyer agreed to, whether the item shipped. Weeks later a dispute arrives, and the seller has to reconstruct all of it by hand, under a deadline, or lose the money.

PayPal already has the rails for the hard part: shipment tracking, the Disputes API, seller protection. What is missing is an agent that collects the evidence *while the purchase happens* and uses it when it matters.

## What it does

1. **Before you pay.** Saves the store's return and warranty terms as they were at checkout, checks the purchase against your bills and payday, and records a SHA-256 fingerprint of exactly what you agreed to (items, amount, payee).
2. **While you pay.** The approval becomes a **signed spending mandate**: an Ed25519 signature over the payee, the maximum amount, the exact items and an expiry. Its hash is written onto the PayPal order (`custom_id`), so PayPal's own record points back to it. Before capture the mandate is checked again and the payment fails closed if anything differs, so an agent, or a prompt-injected product page, cannot add a fee or redirect the money. Checkout runs on PayPal Orders v2. A security gateway (policy as code, independent of the AI) checks an explicit approval for this exact amount and payee, a fraud score, and limits; large or unusual payments need step-up verification. Captures and refunds use deterministic `PayPal-Request-Id` keys and read PayPal before any retry, so a dropped connection never charges twice.
3. **After you pay.** The seller marks the order shipped and the tracking number goes to PayPal (Orders v2 Add Tracking). It comes back into the briefcase as verified evidence.
4. **When a buyer disputes.** PayPal's dispute arrives by webhook (or a manual sync). The agent matches it to the payment, drafts PayPal-shaped evidence from the briefcase (tracking as `PROOF_OF_FULFILLMENT`; the signed mandate, agreed items and saved store terms in the notes), shows the seller a case file with how many of the proofs PayPal needs are on hand, and recommends fighting or accepting. The seller approves the exact draft; only that draft (checked by hash) is sent with `provide-evidence`. Accepting a claim refunds money, so it goes through the same gateway as any refund.
5. **Evidence you can see.** Every purchase shows an evidence ledger: each fact with a seal for who vouches for it (verified by PayPal or a signature, claimed by a person, or inferred by the AI with its sources) and its SHA-256 fingerprint.
6. **Everything else, on the same briefcase:** an assistant you can type or talk to (read-only for money), budget and bill tracking, signed shop QR codes with replay protection, invoice-vs-purchase-order checks for business buyers, and signed buyer and seller agents that share only the fields each side is allowed to see.

## How we use PayPal

Every call below is in `app/paypal/adapter.py` and runs against the real sandbox when `PAYPAL_ENV=sandbox`. The test suite runs the same code against an offline PayPal-shaped mock.

| PayPal API | Used for | Verified in sandbox |
| --- | --- | --- |
| OAuth 2.0 client credentials | Server-side access token | Yes |
| Orders v2: create (with the mandate hash as `custom_id`), get, capture | Checkout with itemized purchase units; capture only after the mandate and the gateway allow it | Yes (hosted demo: order `42072361WU062731N`, capture `8NK10720LK217045H`) |
| Orders v2: Add Tracking (`/v2/checkout/orders/{id}/track`) | Seller shipment tracking attached to the capture | Yes |
| Payments v2: refund | Seller-approved refunds, keyed per case and amount | Mock-tested |
| Disputes v1: list, get, provide-evidence or provide-supporting-info (whichever PayPal's links allow), accept-claim; sandbox adjudicate | Answering buyer disputes from the briefcase | Yes: buyer's "item not received" case `PP-R-ZSX-10198838` on capture `8NK10720LK217045H` was matched, answered with the USPS tracking and agreed terms, and resolved `RESOLVED_SELLER_FAVOUR` |
| Webhooks: signature verification, `CUSTOMER.DISPUTE.*`, `PAYMENT.CAPTURE.*` | Disputes and captures arrive as events; every event is verified with PayPal before it is applied | Yes: the dispute reached the hosted demo by verified webhook |
| PayPal JS SDK Buttons | Buyer approval in a PayPal popup | Yes |
| PayPal's official MCP server (`@paypal/mcp`) | Runs next to ContextIQ's own MCP server in Claude Desktop (`mcp/claude_desktop_config.example.json`) | Config provided |

Not used yet: Invoicing v2 (adapter methods exist, not wired into the app), Payouts, Vault, Subscriptions.

## How we use AI

| Tool | What it does in ContextIQ |
| --- | --- |
| Groq `openai/gpt-oss-120b` and `openai/gpt-oss-20b` | Wording answers, reading store policies and unclear questions. Never moves money, decides eligibility or reports balances. Optional: without a key, plain templates are used. |
| LangGraph | Orchestrates understand → retrieve → experts → explain for the assistant |
| scikit-learn | Question router, personal/business purpose, spending category, fraud (gradient boosting + isolation forest + rules), subscription detection, a decision model for refund remedies |
| PyTorch + PEFT (LoRA) | Optional store-policy sentence model (local only; the hosted demo uses the TF-IDF model) |
| Thompson-sampling bandit | Orders home shortcuts; changes presentation only, never permissions |
| MCP Python SDK | ContextIQ as an MCP server: purchases, refund eligibility, budget, risk checks, dispute drafts. No tool can pay or refund. |

**Model results (synthetic data, from `MODEL_REPORT.md`):** question router macro-F1 0.833 on unseen phrasings; fraud 91–99% of known attack types caught at 2.4% false alarms; subscriptions F1 0.997; spending forecast 18.1% error (baseline 21.3%); refund decision model 100% agreement with the written policy; adaptive home 59% tap rate vs 26% fixed order. All training and test data is synthetic, so these show the methods work, not production accuracy.

## How we built it

FastAPI and SQLAlchemy (SQLite), vanilla JavaScript front end, LangGraph, scikit-learn, the `cryptography` library (Ed25519 signatures for QR codes and agent messages, SHA-256 fingerprints for agreements and evidence), `webauthn` for passkeys, deployed on Render. Supabase Postgres for the hosted demo's data. 37 end-to-end tests run the full API in mock mode on every push (GitHub Actions), which then deploys to Render.

## What's real and what's simulated

- **Real:** PayPal sandbox orders, captures, tracking, dispute responses and webhooks; the security gateway; signed QR codes; the trained models.
- **Simulated:** merchants, suppliers and their data; carrier delivery events (PayPal tracking is real, the "delivered" scan is not); a mock mode for offline demos.
- **Demo shortcuts:** identity is a demo header (no login); the step-up code is shown on screen instead of sent to a phone (passkeys also work); the sandbox "decide" button stands in for PayPal's review team.

## Challenges we ran into

- Our first sandbox dispute skipped straight to PayPal review, where `provide-evidence` is not allowed. The agent now reads PayPal's `links` on the dispute and uses whichever response PayPal accepts at that moment.
- A capture attempted before the buyer approved on PayPal used up the one-time approval. We found it in a real sandbox run and fixed the order of checks.
- Under the current FastAPI, our database commit ran after the response was sent, so a fast client could read stale payment state. Our in-process tests could not see it; an HTTP end-to-end run in a fresh clone did. Fixed by committing before the response.
- Keeping AI output away from money: the model can draft, explain and recommend, but only the gateway turns an approved proposal into a PayPal call.

## What's next

Google A2A agent cards for the buyer and seller agents, mandates as SD-JWT verifiable credentials for interoperability with AP2, Vault for repeat purchases, Payouts for supplier payments, and real sign-in in place of the demo identity header.

## Submission period

This repository was created and built during the hackathon submission period.
