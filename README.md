# ContextIQ

**The AI that keeps working after you pay.** ContextIQ gives every PayPal transaction a memory — an
evidence-backed *briefcase* — and puts one AI orchestrator on top that explains before you buy, remembers
what was promised, and fixes what goes wrong. AI proposes; deterministic code decides whether money moves.

Built for the PayPal AI Hackathon (Devpost) by team Avoflare. Licensed under Apache-2.0.

## Try it

- **Guided judge tour (PayPal sandbox):** https://contextiq-0ihy.onrender.com/?demo=1. A five-step bar at the
  top tracks the real state of your purchase and takes you to each next step, switching between buyer and
  seller for you. It runs on Render's free tier, so the first load after a quiet spell can take about a minute;
  data is kept in Postgres.
- **PayPal sandbox buyer login:** in the Devpost submission's test-credentials field (not in this repo).
- **The five steps:**
  1. **Pay with PayPal** as the buyer: approve in the PayPal popup. Capture only happens if the buyer's signed
     spending mandate and the security gateway both allow it.
  2. **Seller ships** (top-bar switch: *Seller*): open the purchase → *Mark shipped*. The tracking number goes to
     PayPal and appears in the evidence ledger as verified.
  3. **Buyer disputes at PayPal**: as the sandbox buyer at https://www.sandbox.paypal.com, report the item as
     not received. The dispute reaches ContextIQ by verified webhook within a few minutes.
  4. **Answer from the briefcase**: as the seller, *Prepare a response from the briefcase*, review the case file,
     then *Send this evidence to PayPal*.
  5. **PayPal decides**: *Sandbox: ask PayPal to decide*. The console (`/console`) shows every gateway decision.
- **Try to break it:** in any purchase, *Test the signed mandate* has a prompt-injected agent add a hidden fee
  and redirect the payment; both are blocked, with the reason.
- **Identity is a demo header** (`X-User-Id`, set by the Buyer/Seller switch). There is no login; do not reuse
  this pattern in production.

## What it can do

### Before you pay
- **Store terms reader:** extracts the return window, warranty and exclusions from a store's policy, using patterns plus a TF-IDF + LoRA sentence model. Instructions hidden in merchant pages are ignored.
- **Cart intelligence:** the Chrome extension reads your cart only when you click it. It never edits the page or adds affiliate links.
- **Price monitoring:** tracks prices it has actually seen and gives a buy-or-wait verdict checked against your budget.
- **What-if budget check:** "can I afford this?" shows the cash left before payday after pending bills.
- **Dynamic QR:** reads ContextIQ, UPI, EMVCo and PayPal.me codes and shows what each really contains. Shop QR codes are Ed25519-signed with a nonce and an expiry; replayed or tampered codes are blocked.
- **Fraud and risk:** a gradient-boosted model, an Isolation Forest and rules decide when to ask for extra verification (a code or a passkey).
- **Personal vs business:** files each payment to the right account, remembers your answer, and asks only when unsure.

### Paying
- **PayPal integration:** orders, approval, capture, refunds, shipment tracking, disputes and verified webhooks over PayPal's REST API.
- **Signed spending mandates:** the buyer's approval becomes an Ed25519-signed mandate (payee, maximum amount, exact items, expiry) whose hash is stored on the PayPal order; capture fails closed if anything differs. AP2-shaped, our own implementation.
- **Self-healing payments:** after a dropped connection it checks PayPal before retrying, using idempotency keys, so it never charges twice.
- **Security gateway:** every money action needs explicit approval, a permission check, a risk check and limits, and is written to an audit log. Step-up verification starts at $500 ($200 for a new payee).
- **Online and in-person:** online checkouts and counter QR payments are handled differently.

### After you pay
- **Transaction briefcase:** an append-only record per purchase holding the agreement, receipts, terms, deadlines and evidence. Each item is labelled `verified`, `claimed` or `inferred`.
- **Proof of intent:** a hash of exactly what you agreed to, compared with what actually happened.
- **Refunds and replacements:** checks your entitlement (return window, replacement window, warranty), prepares the claim and tracks it. Only the seller can approve a refund.
- **PayPal dispute responses:** when a buyer opens a PayPal dispute, the seller's agent drafts the evidence from the briefcase (PayPal tracking, the agreed items and amount, the saved store terms), recommends fight or accept, and sends only the draft the seller approved.
- **Dispute prevention:** catches invoice vs purchase-order mismatches early and lines up both sides' claims against the evidence.
- **Bills and obligations:** bills, subscriptions, return deadlines and supplier payments, with checklists that tick themselves.

### Money and planning
- **Budgeting:** category spend and pace, recommendations, and a 30-day cash-flow forecast.
- **Investment intelligence (optional):** checks whether money is truly spare and explains options with likely ranges. Company lookups need a free Alpha Vantage key. Education, not advice.
- **1-way notices:** send payment reminders or notices to suppliers or clients.

### Talking to it
- **AI help desk:** ask in your own words by typing or voice. Routing is rules first, then a trained router, then an optional LLM (Groq or Claude) that only words answers and never moves money. Without a key it falls back to templates.
- **Voice (read-only):** browser microphone or a Siri Shortcut. "Pay", "send" and "approve" are refused.
- **Notifications:** the bell, pop-ups and optional device alerts.

### Agents and integrations
- **Buyer and seller agents:** each has a signed identity card and exchanges signed, replay-protected messages, sharing only its allowed fields.
- **MCP server:** seven read-only tools for Claude Desktop or any MCP client.
- **Passkeys:** fingerprint, face or device PIN instead of a step-up code.
- **Phone assistants:** Siri App Intent and Android App Actions code is written but not built.

### Under the hood
- **Orchestrator:** LangGraph runs understand, retrieve, expert, explain.
- **Shared reasoning:** uncertainty, counterfactual, causal and temporal reasoning, a transparent decision model and a temporal knowledge graph.
- **Least-privilege memory:** each expert reads only the memory it is allowed to, so a seller never sees the buyer's budget.
- **Adaptive layer:** a Thompson-sampling bandit reorders home shortcuts and reminder timing. It changes presentation only, never permissions.
- **Smart cache:** repeated work is cached; payment state never is.
- **Security telemetry:** a hash-chained SENTRA-style log with incident correlation and decoy responses for blocked sessions.

The same list, with where each feature lives and how real it is, is in `app/features.py` and on the console page.

## Run it (2 minutes)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # requirements-ml.txt adds torch + peft for training and the LoRA model
cp .env.example .env            # PAYPAL_ENV=mock works offline; see "PayPal sandbox" below
python -m app.ml.train          # trains every model with hyperparameter search (~7 min), writes MODEL_REPORT.md
python run.py                   # http://localhost:8000
pip install -r requirements-dev.txt && pytest -q   # 37 end-to-end tests (mock mode)
python -m app.ml.lora_policy    # optional, needs requirements-ml.txt: LoRA policy model (~12 min on CPU)
python -m app.ml.evaluate_unseen  # final test on unseen, shifted data (~4 min)
```

Switch users (shopper / merchant / supplier) from the bottom of the left rail.
The demo store is at <http://localhost:8000/demo-store/>.

**Two front ends, two audiences.**

- **The app people use: <http://localhost:8000/>.** It tells you things; it doesn't ask. It has five screens:
  - **Home:** scan to pay (a signed shop QR), bills and payments due with days left and a Pay button, what's important right now, the top recommendation, and what you bought this month.
  - **Cart:** price history for every item in your carts, with a buy-or-wait verdict that checks your budget.
  - **Budget:** categories and how fast you're spending, recommendations ("cut dining by $24 a week to afford both"), and a slider to plan a purchase.
  - **Invest:** how much you can safely put away, and options with their likely ranges, explained simply.
  - **History:** the briefcase underneath, with a Personal/Business switch.
  - **Everywhere:** notifications (the bell, pop-ups, and optional device alerts) and an assistant that answers about specific items and follow-ups.
  - **Accounts:** the app picks the account by context. You can switch it in History and on the pay screen before paying.
- **The judges' console: <http://localhost:8000/console>.** It shows every agent, model, signature, security decision and the full list of features.

To replay the setup, delete `data/contextiq.db` and restart, or open the profile button, then *Change my setup*.

### PayPal sandbox

1. developer.paypal.com → Apps & Credentials → **Sandbox** → Create App (Merchant).
2. In `.env`: `PAYPAL_ENV=sandbox`, `PAYPAL_CLIENT_ID=…`, `PAYPAL_CLIENT_SECRET=…`.
3. Create a US Personal (buyer) and US Business (merchant) sandbox account.
4. `python scripts/sandbox_check.py` — runs OAuth → order → your approval → capture → **idempotent retry
   (no second charge)** → partial refund → disputes → balance against the real sandbox.
5. Webhooks: expose port 8000 (e.g. `ngrok http 8000`), add a webhook to `…/api/webhooks/paypal`,
   put its ID in `PAYPAL_WEBHOOK_ID`.

`.env` is git-ignored. Never commit it.

### Reasoning model (optional, free)

Get a free key at console.groq.com, then in `.env`: `LLM_PROVIDER=groq` and `GROQ_API_KEY=…`.
The model is used only to word answers, read store policies and understand unclear questions — never to
move money, decide eligibility or report balances. Without a key, everything still works with plain templates.
(Claude works too: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…`, paid per use.)

### Voice

* **In the browser:** tap the microphone in the top bar (Chrome, Edge or Safari). Answers are spoken back.
* **Siri (iPhone/Mac):** Shortcuts app → new shortcut → *Dictate Text* → *Get Contents of URL*:
  `POST https://<your-public-url>/api/voice`, headers `X-Voice-Token: <VOICE_TOKEN>` and `X-User-Id: alex`,
  JSON body `{"text": <Dictated Text>}` → *Get Dictionary Value* `speech` → *Speak Text*. Name it "Ask ContextIQ".
  Your computer needs a public URL (e.g. `ngrok http 8000`).
* **Android:** use the microphone in the web app in Chrome. A Gemini/Assistant app action isn't built yet.
* Voice is **read-only**: "pay", "send", "approve" and "confirm" are refused — money actions need the screen.

### Passkeys

Trust → **Set up a passkey**. When a payment needs extra verification, choose **Use my passkey** (fingerprint, face
or device PIN) instead of the code. Works on `http://localhost:8000` in Chrome, Edge and Safari; for any other
address set `PUBLIC_BASE_URL` to that exact origin (passkeys are tied to it).

### Agent-to-agent (buyer ↔ seller)

Activity → a purchase with a connected seller → **Connect with the seller's agent**. Each agent has a registry-signed
identity card (Ed25519); every message is signed and checked for freshness and replays; each side shares only its
allowed fields; *Test: tamper with a message* shows a rejected message. Both agents run on this server today;
`POST /a2a/inbox` accepts envelopes from agents registered with this server's registry key. Cross-instance
discovery (Google A2A agent cards) is future work.

### MCP server (use ContextIQ from Claude Desktop or any MCP client)

```json
{"mcpServers": {"contextiq": {"command": "python", "args": ["-m", "app.mcp_server"],
  "cwd": "/path/to/contextiq", "env": {"CONTEXTIQ_USER": "alex"}}}}
```
Tools: list_purchases, get_purchase, check_refund_eligibility, budget_status, can_i_afford,
assess_payment_request, ask. None can pay or refund. Every call passes the plugin registry (scopes, rate limits,
audit) — see Trust → *Connected tools*.

### Market data (optional investing)

Free key at alphavantage.co → `ALPHAVANTAGE_API_KEY=` in `.env`. Money → *Look up a company*.

### Phone assistants

See `mobile/README.md` (Siri App Intent and Android App Actions code — written, not built here).

### Chrome extension

`chrome://extensions` → Developer mode → Load unpacked → `extension/`. Open the demo store and click the
ContextIQ icon. It reads the cart only when you click, never edits the page, and never inserts affiliate links.

## What's real and what's simulated

| Part | Status |
| --- | --- |
| PayPal Orders v2 (create, get, capture), Add Tracking | Real REST calls (`app/paypal/adapter.py`), verified against the sandbox |
| PayPal Disputes v1 (list, get, provide-evidence / provide-supporting-info, accept-claim, sandbox adjudicate), webhook verification | Real REST calls; a buyer "item not received" dispute was answered and resolved in the seller's favour in sandbox |
| PayPal refunds | Real REST calls; tested against the PayPal-shaped mock |
| PayPal Invoicing v2 | Adapter methods only; not wired into the app yet |
| Carrier delivery scan ("Mark delivered") | Simulated; PayPal tracking is real |
| Self-healing payment, duplicate-charge protection | Real (`PayPal-Request-Id` + read-before-retry) |
| Security gateway, approvals, step-up, audit | Real, policy as code |
| Signed QR (Ed25519, nonce, expiry, replay block) | Real |
| Trained models (router, purpose, category, fraud, subscriptions, cash-flow forecast) | Real models, **synthetic training data** |
| Merchant, supplier, delivery events | Simulated demo accounts and data |
| Bank / wallet balances outside PayPal | Not connected; user-entered and labelled as such |
| Live market data for investing | Not connected; education and liquidity checks only |

## Architecture

```
Web app · Cart extension · Merchant counter (QR)
                │
     Central orchestrator (LangGraph): understand → retrieve → expert → explain
                │   rules first · trained router fallback · optional GenAI
   ┌────────────┼──────────────┬───────────────┐
 Before pay   Payment        After pay        Risk & context
 policy, cart, checkout,     refund, help     fraud, purpose,
 budget what-if recovery, QR desk, invoice    channel
                │
 Shared reasoning: uncertainty · counterfactual · causal · temporal · decision model
                │
 Security gateway (approval · permission · risk · limits · idempotency · audit)
                │                              ▲
          PayPal adapter ──► PayPal ── verified webhooks ──► Transaction briefcase
```

* **Briefcase** (`app/briefcase.py`, `app/models.py`): append-only event log; evidence labelled
  `verified` (PayPal / signed), `claimed` (a person said it) or `inferred` (AI, must cite evidence).
  Proof of intent = hashed agreement. Archived only when every obligation is closed.
* **Least-privilege memory** (`app/intelligence/memory.py`): each expert reads only the memory kinds it is
  allowed; a seller's view never contains the buyer's budget.
* **Decision model** (`app/intelligence/decision.py`): transparent weighted scoring over permitted options;
  order-invariant by construction.
* **Adaptive layer** (`app/intelligence/adaptive.py`): Thompson-sampling bandit for shortcut order and
  reminder timing; changes presentation only, never permissions; feedback clipped against poisoning.
* **Security** (`app/security/`): gateway, Ed25519 message signing, SENTRA-style telemetry with a hash chain
  and incident correlation, isolated decoy responses for blocked sessions, prompt-injection filtering of
  merchant pages.

## Model results (synthetic data)

See `app/ml/models/report.md` after training. Highlights: purpose classifier evaluated on users **and**
merchant names never seen in training; fraud evaluated per attack family, with two families held out
entirely and written in a separate generator (`app/ml/redteam.py`). Synthetic data is easier than real data —
treat these as a pipeline check, not production accuracy. Next step: external check on PaySim / IEEE-CIS.

## Demo script (≈3 min)

1. Demo store → **Pay with ContextIQ** → *Check before paying*: return terms explained, hidden prompt
   injection ignored, budget what-if, price history.
2. *Agree and continue* → approve on PayPal → tick *Simulate a dropped connection* → *Complete payment*:
   step-up for a new payee, then the connection drops and ContextIQ shows **1 charge at PayPal**.
3. Briefcase: stamps show who vouches for each fact. As the seller, *Mark shipped* (tracking goes to PayPal);
   as the buyer, *Can I return this?*
3b. Buyer opens a PayPal dispute → seller *Prepare a response from the briefcase* → approve → evidence goes to
   PayPal.
4. Ask: "Why does my supplier say payment wasn't received?" → PayPal-verified answer, don't pay twice.
5. Business: invoice vs purchase order mismatch caught before payment; signed counter QR (replay rejected).
6. Trust: fraud catch rate per attack type, gateway decisions, cache and token metrics.
