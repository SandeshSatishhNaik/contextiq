# ContextIQ — 3-Minute Demo Video Walkthrough Script

> **Target Duration:** 3 minutes (180 seconds)  
> **Key Goal:** Show hackathon judges a live, working, end-to-end PayPal checkout with deep AI context, fraud defense, and multi-remedy post-purchase actions (Refund, Free Swap / Replacement, Warranty, and Dispute).

---

## 🎬 Video Recording Setup Checklist

1. **Browser Windows Ready**:
   - Tab 1: `http://localhost:8000/` (ContextIQ Main User App)
   - Tab 2: `http://localhost:8000/console` (Live Agent & Specialist Telemetry Console)
   - Tab 3: Incognito Window with PayPal Sandbox Checkout ready.
2. **Audio**: Clean microphone, brisk and confident pacing.
3. **Reset State**: Click the `↺ Reset Demo` button on `http://localhost:8000/console` right before starting recording.

---

## ⏱️ Video Script (Second-by-Second)

### 0:00 – 0:30 | The Hook & The Problem
**Visual:** Show a traditional shopping cart or the ContextIQ home screen (`http://localhost:8000`).  
**Voiceover:**  
> "Every day, billions of dollars move through payment buttons that are completely blind to context. A checkout button knows your card number and the price—but it doesn't know that your rent is due in 3 days, it doesn't know what return or swap policy the store promised, and it completely forgets about you the moment the payment clears.
> 
> This is **ContextIQ**. We built an autonomous financial intelligence system that transforms PayPal from a passive payment rail into an active, context-aware guardian."

---

### 0:30 – 1:15 | Pre-Purchase Intelligence & Multi-Agent Telemetry
**Visual:**  
1. On `http://localhost:8000`, click into the chat bar: *"Can I afford the earbuds?"*
2. Switch quickly to `http://localhost:8000/console` to show the 4 parallel specialists (`price`, `budget`, `policy`, `evidence`) lighting up with live telemetry traces.
3. Switch back to the chat to show the structured synthesis.

**Voiceover:**  
> "Watch what happens when I ask ContextIQ: *'Can I buy the earbuds?'*
> 
> Under the hood, ContextIQ doesn't just call a generic chatbot. It dispatches four specialist agents in parallel:
> - The **Price Expert** tracks historical price drops across merchants.
> - The **Budget Expert** evaluates our $1,450 cash on hand against committed upcoming bills.
> - The **Policy Expert** inspects the store's terms, catching hidden exclusions like unsealed hygiene restrictions.
> - And the **Evidence Expert** prepares a cryptographic briefcase.
> 
> Here on the console, you see the real-time consensus. The AI tells us: the price dropped $20, but with rent approaching, our safe spendable cash will be tight."

---

### 1:15 – 1:55 | Live PayPal Sandbox Checkout & Autonomous Briefcase
**Visual:**  
1. Click the **"Buy with PayPal"** button on the cart or prompt.
2. The PayPal Sandbox approval popup opens.
3. Complete the checkout (or show the approved order).
4. Click over to the **Activity / Briefcase** tab on ContextIQ.
5. Expand the newly created Case to show the **cryptographic SHA-256 agreement hash, policy snapshot, and PayPal Capture ID**.

**Voiceover:**  
> "Now let's proceed to checkout. ContextIQ connects directly to PayPal's Orders v2 API. Notice that the order is bound to a deterministic `PayPal-Request-Id` and anchors our briefcase reference ID right in the purchase unit.
> 
> Once approved and captured via PayPal's capture endpoint, ContextIQ locks the transaction into an **Autonomous Transaction Briefcase**. 
> 
> It captures an immutable snapshot of the merchant's exact return policy, an Ed25519-signed proof of intent, and the PayPal capture receipt. If the seller later changes their terms or disputes delivery, the proof is mathematically indisputable."

---

### 1:55 – 2:25 | Security, Attack Defense & B2B Invoice Verification
**Visual:**  
1. On the console or app, show the Fraud Defense and Invoicing section.
2. Show a supplier notice or invoice from *Nova Parts*.
3. Highlight the invoice discrepancy alert (+11.6% inflation attempt).

**Voiceover:**  
> "Security is where ContextIQ truly shines. In our benchmark testing, our cryptographic layer caught 100% of contract tampering, replayed QR nonces, and forged signature attacks.
> 
> When tested against a stream of 10,000 transactions where attackers disguised 60% of their anomalous signals, our 3-layer AI ensemble caught 84% of stealth attacks while keeping false alarms under 3.8%.
> 
> And for B2B buyers, ContextIQ automatically matches incoming invoices against signed purchase orders—instantly flagging unagreed surcharges and holding payment before money moves."

---

### 2:25 – 3:00 | Multi-Remedy Execution: Swaps, Refunds, Warranty & Disputes
**Visual:**  
1. Open a completed purchase in **Activity / History** (e.g. Mechanical Keyboard or Earbuds).
2. Click **"Something wrong with it?"** (or click **"Can I return this?"** on `/console`).
3. Point out the multiple available remedies rendered dynamically:
   - **`[Request Free Swap / Replacement]`**
   - **`[Ask for PayPal Refund]`**
   - **`[Claim Warranty Repair]`**
   - **`[Escalate to PayPal Purchase Protection]`**
4. Click **`Request Free Swap / Replacement`** & show the instant confirmation and briefcase update!

**Voiceover:**  
> "Finally, ContextIQ doesn't abandon you after checkout. It tracks your deadlines. And it doesn't just offer basic refunds—it dynamically evaluates and executes whatever remedy fits your situation:
> - You can trigger a **Free Swap / Unit Replacement** if an item arrives defective,
> - Claim a **Manufacturer Warranty**,
> - Request a **Full PayPal Refund**, or
> - Escalate to **PayPal Purchase Protection**.
> 
> When I click *Request Free Swap*, ContextIQ anchors the swap request directly into the briefcase and notifies the merchant to dispatch a replacement.
> 
> ContextIQ makes PayPal checkout safer before you pay, resilient while you pay, and protective long after. Thank you!"

---

## 💡 Quick Tips for High Marks
- **Show the Live Swap**: Clicking *Request Free Swap* shows judges that ContextIQ goes far beyond basic refund APIs into full post-purchase lifecycle management.
- **Show PayPal Order IDs**: Pointing out real PayPal Order and Capture tokens (e.g. `10K46769T1581584C`) proves deep API integration.
- **Keep it under 3 minutes**: Hackathon judges often penalize videos that run past 3:00.

