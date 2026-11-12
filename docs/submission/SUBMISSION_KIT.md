# ContextIQ: Devpost submission kit

Paste each section into the matching Devpost field. The images are in this folder, numbered in gallery order.

---

## Project name
ContextIQ

## Tagline (Devpost "elevator pitch")

**Use this one:**
> The AI agent that keeps working after you pay: every PayPal payment gets an evidence briefcase, and disputes get answered from it.

Alternatives, if you want a different tone:
1. Checkout forgets everything. ContextIQ remembers, and wins the PayPal dispute with it.
2. An AI agent for PayPal that collects evidence while you buy and spends it when a dispute comes.
3. Signed spending mandates for AI shoppers, and dispute answers built from real PayPal evidence.
4. From "Pay with PayPal" to "Closed in your favour": evidence for every payment, automatically.
5. AI that can't overspend, and a briefcase that wins disputes.

---

## Links
- **Try it (guided judge tour):** https://contextiq-0ihy.onrender.com/?demo=1
- **Code (Apache-2.0):** https://github.com/SandeshSatishhNaik/contextiq
- **Demo video (YouTube, public, 2:54):** https://youtu.be/cGJgYqDmotg
- **Test credentials** (Devpost field, not in the repo): the login of a **dedicated PayPal sandbox buyer account** you create for judges at developer.paypal.com → Sandbox → Accounts. Add one line: "Sandbox only: test money, no real payments."

---

## Story (Devpost "About the project")

### Inspiration
Checkout knows a card number and an amount, and forgets everything else the moment the payment completes: what the store promised, what exactly the buyer agreed to, whether the item ever shipped. Weeks later a dispute arrives, and the seller has to rebuild that story by hand, under a deadline, or lose the money. Card chargebacks alone are forecast to cost **$33.79 billion worldwide in 2025**, rising to $41.69 billion by 2028 ([Mastercard, 2025 State of Chargebacks](https://www.mastercard.com/hk/en/news-and-trends/Insights/2025/what-s-the-true-cost-of-a-chargeback-in-2025.html)).

At the same time, AI agents are starting to shop for people, and an agent that can be talked into adding a fee or paying the wrong account is a new way to lose money. PayPal already has the rails for both problems: Orders, shipment tracking, the Disputes API and buyer and seller protection. What was missing was an agent that **collects the evidence while the purchase happens** and **uses it when PayPal asks**, without ever being trusted to move money on its own.

### What it does
- **Before you pay:**
  - Saves the store's return and warranty terms exactly as they were at checkout, and flags hidden exclusions (and hidden prompt-injection text on the page).
  - Checks the purchase against your bills and payday.
- **While you pay:**
  - The approval becomes a **signed spending mandate**: an Ed25519 signature over the payee, the maximum amount, the exact items and an expiry.
  - Its hash is written onto the PayPal order (`custom_id`), so PayPal's own record points back to it.
  - Capture fails closed if anything differs. A prompt-injected page that tells the agent to add a fee or pay another account gets blocked, with the reason shown.
  - A security gateway (policy as code) also checks explicit approval, a fraud score and step-up.
  - Every PayPal call is idempotent and reads PayPal before any retry, so a dropped connection never charges twice.
- **After you pay:**
  - The seller marks the order shipped and the tracking number goes to PayPal (Add Tracking).
  - Every sale shows a **dispute-readiness meter**: how many of the five proofs PayPal weighs are already on file.
- **When a buyer disputes:**
  - PayPal's dispute arrives by verified webhook and is matched to the payment.
  - The agent builds a **case file**: the buyer's claim next to what the briefcase proves. It recommends fighting or accepting and drafts PayPal-shaped evidence.
  - The seller approves the exact draft. Only that draft is sent, through whichever response PayPal's API allows at that moment.
  - In our sandbox run, PayPal resolved the case **in the seller's favour** (`PP-R-CZZ-10198932`).
- **Everywhere:**
  - An **evidence ledger** on every purchase shows each fact with a seal for who vouches for it: verified by PayPal or a signature, claimed by a person, or inferred by the AI. Each fact has its fingerprint.
  - An assistant you can type or talk to. Voice can ask, but never pay.
  - Also: budgets, bills, signed shop QR codes with replay protection, invoice-vs-purchase-order checks, signed buyer and seller agents, and an MCP server that runs next to PayPal's own MCP server.

### How we built it
- **App:** FastAPI and SQLAlchemy, with a vanilla-JavaScript front end and a judges' console. It's deployed on Render, with GitHub Actions running the tests on every push.
- **PayPal:** Orders v2 (with `custom_id`), capture and refunds, Add Tracking, and Disputes v1 (list, get, provide-evidence, provide-supporting-info, accept-claim, and the sandbox-only adjudicate). Webhooks are signature-verified. The JS SDK handles buyer approval. PayPal's MCP server (`@paypal/mcp`) runs alongside ours.
- **AI:** Groq-hosted gpt-oss models for wording and reading policies. Scikit-learn models for routing, purpose, category, fraud, subscriptions and the cash-flow forecast. A LoRA policy-sentence model with PEFT. A learned decision model and a Thompson-sampling bandit. LangGraph orchestrates 12 experts.
- **Security:** Ed25519 signatures (`cryptography`), SHA-256 fingerprints, nonces and expiry, and WebAuthn passkeys.

### Challenges we ran into
- **The first real sandbox dispute skipped straight to PayPal review,** where `provide-evidence` is refused. The agent now reads the dispute's `links` and uses whichever response PayPal accepts.
- **A capture attempted before the buyer approved burned the one-time approval.** We found it in a live sandbox run and fixed the order of checks.
- **The database commit ran after the response was sent** under the current FastAPI, so a fast client could read stale payment state. Only an end-to-end HTTP run in a fresh clone showed it.
- **The reasoning model spent its whole token budget thinking,** so answers came back empty. We set low reasoning effort, and incomplete replies fall back to our own text.
- **The injection filter worked line by line,** so one injected sentence could erase a store's real terms. It now filters sentence by sentence.
- **Synthetic training data didn't carry over to real brands** for spending categories (60%). Well-known merchants are now matched first and unsure ones are left for the user: 0 wrong on 22 fresh merchants.

### Accomplishments that we're proud of
- A real PayPal sandbox dispute: answered from evidence gathered at checkout, approved by a person, and decided in the seller's favour.
- Signed mandates whose hash lives on PayPal's own order record, verified on real sandbox orders.
- Fraud checks re-calibrated on separate data. On an untouched test stream: 94% of attacks caught at 2.7% false alarms, down from 5.4%.
- 42 end-to-end tests and 39 agent-level checks, all passing. The AI can never move money; tests prove forged and replayed approvals are refused.

### What we learned
- Live sandbox runs find the bugs that unit tests can't.
- "Verified" has to mean verified. Labelling every fact by who vouches for it changed how we designed every screen.
- A small deterministic layer (mandate, gateway, idempotency) is what makes an AI agent safe enough to touch money.

### What's next for ContextIQ
- Mandates as SD-JWT verifiable credentials, for interoperability with AP2.
- Google A2A agent cards for the buyer and seller agents.
- Vault for repeat purchases and Payouts for suppliers.
- Real sign-in instead of the demo identity header.
- Training on real, consented transaction data.

---

## Built with (Devpost tags)
`python` `fastapi` `sqlalchemy` `javascript` `html5` `css3` `paypal` `paypal-orders-api` `paypal-disputes-api` `paypal-webhooks` `paypal-mcp` `groq` `gpt-oss` `langgraph` `scikit-learn` `pytorch` `peft` `lora` `mcp` `ed25519` `webauthn` `render` `github-actions` `sqlite` `postgresql`

## Tools: AI models and services, and how they're used
| Tool | How ContextIQ uses it |
|---|---|
| **Groq: `openai/gpt-oss-120b` and `openai/gpt-oss-20b`** | Words the assistant's answers from the app's real figures. Reads store policies. Handles unclear questions. It never moves money, decides eligibility or reports balances; code does. Runs at low reasoning effort, and without an API key the app falls back to templates. |
| **LangGraph** | Orchestrates the assistant: understand, plan, run experts in parallel (12 experts), reason, decide, gate, respond. |
| **scikit-learn models (trained by us)** | Question router, personal vs business purpose, spending category (with a brand keyword map and confidence gate), fraud (gradient boosting + isolation forest + rules), subscription detection, cash-flow forecast. |
| **PyTorch + PEFT (LoRA)** | A store-policy sentence classifier, used together with a TF-IDF model. The hosted demo runs TF-IDF only. |
| **Learned decision model and Thompson-sampling bandit** | Ranks refund remedies to agree with the written policy; orders the home screen's shortcuts. |
| **Model Context Protocol** | ContextIQ as an MCP server (purchases, refund eligibility, budget, risk, dispute drafts; no tool can pay). A ready config runs it next to **PayPal's MCP server** (`@paypal/mcp`). |
| **PayPal REST APIs and JS SDK** | Orders v2, capture, refunds, Add Tracking, Disputes v1, webhooks with signature verification, and buyer approval in the PayPal popup. |
| **Claude Code (Anthropic)** | AI coding assistant used during development. |

Model results come from held-out tests with a fresh seed, on synthetic data:
- **Router:** 88–89% on unseen messages.
- **Fraud:** 94% caught at 2.7% false alarms.
- **Subscriptions:** F1 0.996.
- **Forecast:** 19.7% error, and its 80% range held the real total 83% of the time.
- **Refund decision model:** 100% agreement with the written policy.

---

## Gallery (upload in this order)
| File | Caption |
|---|---|
| `01-cover.jpg` | ContextIQ: the AI agent that keeps working after you pay. |
| `02-home-judge-tour.jpg` | The judge tour tracks the real flow: pay, ship, dispute, answer, PayPal decides. |
| `03-check-before-paying.jpg` | Before paying: the store's terms are saved, a hygiene exclusion is flagged, and the account is chosen. Then PayPal checkout. |
| `04-evidence-ledger.jpg` | The evidence ledger: every fact with who vouches for it, including the signed spending mandate. |
| `05-mandate-blocks-overspend.jpg` | A prompt-injected fee and a redirected payee, both blocked by the signed mandate. |
| `06-seller-dispute-readiness.jpg` | Seller view: dispute readiness, 4 of 5 proofs on file, and what to do about the gap. |
| `07-dispute-case-file.jpg` | A real PayPal sandbox dispute: the buyer's claim next to what the briefcase proves. |
| `08-dispute-won-on-paypal.jpg` | PayPal closed the case in the seller's favour (sandbox case PP-R-CZZ-10198932). |
| `09-console-trust.jpg` | The judges' console: fraud checks and security decisions, measured. |
| `10-how-it-works.jpg` | How it works: AI proposes, deterministic code decides. |

Images 07 and 08 are frames from the demo video. All others are screenshots of the live hosted app.

---

## Requirements checklist
| Requirement | Status |
|---|---|
| Project built with the required tools (PayPal + AI) | ✅ PayPal Orders, Tracking, Disputes, Webhooks, MCP; Groq LLM, LangGraph, trained models |
| Text description of features and functionality | ✅ The story above |
| Functional demo: hosted URL **or** run instructions | ✅ Both: https://contextiq-0ihy.onrender.com/?demo=1, and README "Run it" |
| Tools: which AI models or services, and how | ✅ The Tools table above |
| Public repo with all source, assets and run instructions | ✅ github.com/SandeshSatishhNaik/contextiq |
| Open-source license visible in the repo's About section | ✅ Apache-2.0, detected by GitHub |
| Demo video under 3 minutes | ✅ 2:54 (`ContextIQ_demo.mp4`) |
| Video shows the project working on its target device | ✅ The web app in a desktop browser, on the real PayPal sandbox |
| Video on YouTube, public, linked on the form | ✅ https://youtu.be/cGJgYqDmotg (Public, not made for kids); paste it on the form |
| No third-party trademarks or copyrighted music without permission | ✅ No music. Only PayPal's own sandbox UI (the hackathon sponsor), the PayPal button from PayPal's SDK, and a Mastercard statistic cited as text. No other brands' logos. |
| Test credentials for judges | ⬜ **Your step:** add a dedicated sandbox buyer login in the Devpost field |
| Chrome "Dangerous site" warning | ⬜ **Your step:** finish the Search Console review request (verification file is live) |
