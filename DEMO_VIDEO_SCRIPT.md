# ContextIQ demo video: shot list (target 2:50, hard limit 3:00)

Record on the hosted demo (https://contextiq-0ihy.onrender.com) in PayPal sandbox mode, so every ID on screen is a real PayPal sandbox ID. Open the site a few minutes early so the free instance is awake.

**Before recording**
- Tab 1: the app as **Alex** (buyer).
- Tab 2: the app as **BrightMart** (seller). Use the user switcher; it's a demo header, not a login.
- Tab 3: https://www.sandbox.paypal.com, logged in as the sandbox buyer.
- Do one dry run end to end. Sandbox disputes can take a few minutes to appear, so open the dispute in the dry run and keep that purchase for the dispute scenes if needed.

| Time | Screen | Say (roughly) |
| --- | --- | --- |
| 0:00–0:15 | Title, then the app home | "Checkout forgets everything the moment you pay. When a dispute comes weeks later, the seller has to rebuild the story by hand. ContextIQ is an AI agent on PayPal that keeps the evidence and uses it." |
| 0:15–0:40 | Cart → *Check before paying*: saved store terms, budget check | "Before paying, it saves the store's terms as they are right now, checks the purchase against Alex's bills and payday, and fingerprints exactly what Alex agrees to." |
| 0:40–1:05 | *Pay with PayPal* → PayPal sandbox popup → approve → captured; show the order and capture IDs | "This is a real PayPal sandbox order. Capture only happens after our security gateway checks Alex's explicit approval of this amount and payee. The AI can't move money; the gateway decides." |
| 1:05–1:20 | Tab 2 (BrightMart): open the purchase → *Mark shipped* | "The seller ships. The tracking number goes straight to PayPal with Add Tracking and comes back as verified evidence." |
| 1:20–1:35 | Tab 3: sandbox buyer opens an *Item not received* case | "Now the buyer says it never arrived and opens a PayPal dispute." |
| 1:35–2:15 | Tab 2: *Check PayPal for disputes* → dispute card → *Prepare a response from the briefcase*: recommendation, facts, PROOF_OF_FULFILLMENT | "PayPal's dispute arrives. The agent matches it to the payment, reads the briefcase and drafts the response PayPal asks for: tracking as proof of fulfillment, plus what the buyer agreed to and the store's terms. It recommends fighting, and says why." |
| 2:15–2:35 | *Approve & send this evidence to PayPal* → *Sandbox: ask PayPal to decide* → resolved in the seller's favour | "Nothing goes out until the seller approves, and only the exact draft they saw is sent. In sandbox we can ask PayPal to decide: seller's favour." |
| 2:35–2:50 | Quick montage: console gateway log, signed QR replay rejected, voice refusing to pay, MCP config | "Every decision is logged. QR codes are signed and can't be replayed. Voice can ask, but never pay. And it runs alongside PayPal's own MCP server. ContextIQ: the agent that keeps working after you pay." |

**Rules for the recording**
- Show real IDs only; never show `.env`, the Render dashboard secrets or the sandbox buyer password.
- If a sandbox step stalls, cut and re-record that scene rather than switching to mock mode on camera.
- Upload to YouTube as **Public**, "No, it's not made for kids", under 3:00. Paste the link into Devpost.
