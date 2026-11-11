# Why PayPal

## The thesis

An AI shopping agent is only as trustworthy as what happens after the payment. PayPal already owns that part: buyer and seller protection, shipment tracking, and a disputes process with clear evidence rules. ContextIQ is an agent built around it. It gathers evidence while the purchase happens and spends it when PayPal asks for it.

## Where PayPal does the work

1. **Orders v2 and capture.** Checkout is a PayPal order with itemized purchase units and the ContextIQ case id as `reference_id`. Capture happens only after the security gateway allows it: an explicit approval of this exact amount and payee, a fraud score, and step-up for large or unusual payments.
2. **Idempotency and self-healing.** Each case has deterministic `PayPal-Request-Id` keys (`order-…`, `capture-…`, `refund-…-amount`). After a timeout, ContextIQ reads PayPal before retrying (exponential backoff: 0.2 s, 0.4 s, 0.8 s), so one purchase is never charged twice.
3. **Add Tracking.** When the seller ships, the tracking number is attached to the capture with `/v2/checkout/orders/{id}/track`. This is the evidence PayPal needs for an "item not received" claim.
4. **Disputes v1.** `CUSTOMER.DISPUTE.*` webhooks (or a sync) bring the dispute in. The agent drafts `provide-evidence` from the briefcase, the seller approves the exact draft, and only that draft is sent. Accepting a claim is a refund and passes the gateway. In sandbox, `require-evidence` and `adjudicate` let a judge see the whole case resolve.
5. **Webhooks.** Every incoming event is checked with PayPal's verify-webhook-signature before it changes anything. Repeated deliveries are dropped.
6. **PayPal's MCP server.** `mcp/claude_desktop_config.example.json` runs `@paypal/mcp` next to ContextIQ's MCP server. PayPal's tools act on PayPal; ContextIQ adds the evidence and the judgment, and none of its tools can move money.

## What it changes

| Without ContextIQ | With ContextIQ on PayPal |
| --- | --- |
| The seller rebuilds a dispute from emails and memory, under a deadline | The evidence pack is drafted from what PayPal and the buyer already confirmed |
| Store terms change after the sale | The terms seen at checkout are saved with the purchase |
| A dropped connection during capture can lead to a second charge | Retries reuse the same request id and check PayPal first |
| An AI agent with payment access can be talked into spending | The agent only proposes; the gateway and a person approve |
