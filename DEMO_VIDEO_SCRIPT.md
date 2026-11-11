# ContextIQ demo video: shot list (target 2:50, hard limit 3:00)

Record on the hosted guided tour, https://contextiq-0ihy.onrender.com/?demo=1, in PayPal sandbox mode, so every ID on screen is a real sandbox ID. Open it a few minutes early so the free instance is awake.

**Before recording**
- One browser window on the tour. The **Buyer / Seller** switch in the top bar changes who you are; the tour bar tells you which role each step needs.
- A second tab: https://www.sandbox.paypal.com, logged in as the sandbox buyer.
- Do a full dry run first. Sandbox disputes take a few minutes to arrive and the sandbox decision another minute or two, so file the dry-run dispute early and use that purchase for scenes 6 to 8 if needed.

| # | Time | Screen | Say (roughly) |
| --- | --- | --- | --- |
| 1 | 0:00–0:12 | Home with the judge tour bar | "Checkout forgets everything the moment you pay. When a dispute arrives weeks later, the seller has to rebuild the story by hand. ContextIQ is an AI agent on PayPal that keeps the evidence and uses it." |
| 2 | 0:12–0:35 | Cart → *Buy* → check-before-paying sheet (store terms, budget) | "Before paying, it saves the store's terms as they are now and checks the purchase against Alex's bills and payday." |
| 3 | 0:35–0:58 | *Pay with PayPal* → sandbox popup → approve → Paid. Tour step 1 ticks. | "Alex's approval becomes a signed spending mandate: this payee, this amount, these exact items. Its hash is written onto the PayPal order. Capture only happens if the mandate and our security gateway both pass." |
| 4 | 0:58–1:15 | Open the purchase → evidence ledger → *Test the signed mandate* → two attempts blocked | "Here's why that matters. A prompt-injected product page tells the agent to add a fee and pay a different account. Both are blocked, with the reason. The AI can't move money; the mandate decides." |
| 5 | 1:15–1:30 | Tour → *Switch to seller* → *Mark shipped*; ledger shows tracking as verified | "The seller ships. The tracking number goes straight to PayPal and comes back as verified evidence." |
| 6 | 1:30–1:42 | Sandbox tab: buyer reports *Item not received* | "Now the buyer says it never arrived and opens a PayPal dispute." |
| 7 | 1:42–2:20 | Seller: dispute case file (claim vs proofs, strength meter, verdict) | "PayPal's dispute arrives by webhook. The agent matches it to the payment and builds a case file: what the buyer claims, next to what the briefcase proves: the capture, the signed mandate, the store terms, PayPal tracking. Five of five proofs, so it recommends responding, and says why." |
| 8 | 2:20–2:38 | *Send this evidence to PayPal* → *Sandbox: ask PayPal to decide* → closed in the seller's favour; tour shows all five ticks | "Nothing goes out until the seller approves, and only this exact draft is sent. PayPal's sandbox decides: seller's favour." |
| 9 | 2:38–2:50 | Quick cut: console gateway log, MCP config | "Every decision is audited, and it runs alongside PayPal's own MCP server. ContextIQ: the agent that keeps working after you pay." |

**Rules for the recording**
- Show real IDs only. Never show `.env`, the Render or Supabase dashboards, or the sandbox buyer password.
- If a sandbox step stalls, cut and re-record that scene rather than switching to mock mode on camera.
- Upload to YouTube as **Public**, "No, it's not made for kids", under 3:00. Paste the link into Devpost.
