"use strict";
/* ContextIQ web app — plain JS, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const state = { user: localStorage.getItem("ciq-user") || "alex", config: {}, cart: null, checkout: null, caseId: null, chat: [] };

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SYM = { USD: "$", INR: "₹", EUR: "€", GBP: "£" };
const money = (n, cur = state.config.currency || "USD") => n == null ? "—" :
  `${n < 0 ? "-" : ""}${SYM[cur] || cur + " "}${Math.abs(Number(n)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const nice = (s) => esc(String(s || "").replace(/_/g, " "));
const STAMP = { verified: "Verified", claimed: "Claimed", inferred: "Inferred" };
const stamp = (p, by) => `<span class="stamp ${esc(p)}" title="${esc(STAMP[p] || p)}${by ? " by " + esc(by) : ""}">${esc(STAMP[p] || p)}</span>`;
const SYS = { payments: "Payments", briefcase: "Briefcase", ai: "AI", money: "Money", security: "Security", connect: "Connect" };
const sys = (k) => `<span class="sys ${k}">${SYS[k]}</span>`;

const ICON = {
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  pay: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 7l9-4 9 4v10l-9 4-9-4z M3 7l9 4 9-4M12 11v10"/></svg>',
  refund: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 12a8 8 0 1 0 3-6.2M4 4v5h5"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4"/></svg>',
  tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 12V3h9l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>',
  qr: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3h-3zM20 17v4h-3"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 2h8l5 5v15H6z M14 2v5h5M9 13h7M9 17h7"/></svg>',
  invest: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 12l5 5 9-10"/></svg>',
};
const moneyBtn = (id, label, kind = "btn-money") => `<button class="btn ${kind}" id="${id}">${ICON.lock}${esc(label)}</button>`;

const b64u = { dec: (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0)).buffer,
  enc: (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") };
async function passkeyRegister() {
  const o = await api("/api/passkeys/register/options", { method: "POST" });
  const cred = await navigator.credentials.create({ publicKey: { ...o, challenge: b64u.dec(o.challenge), user: { ...o.user, id: b64u.dec(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) } });
  return api("/api/passkeys/register/verify", { body: { id: cred.id, rawId: b64u.enc(cred.rawId), type: cred.type,
    response: { clientDataJSON: b64u.enc(cred.response.clientDataJSON), attestationObject: b64u.enc(cred.response.attestationObject),
      transports: cred.response.getTransports ? cred.response.getTransports() : [] } } });
}
async function passkeyConfirm(approvalToken) {
  const o = await api("/api/passkeys/auth/options", { body: { approval_token: approvalToken } });
  const a = await navigator.credentials.get({ publicKey: { ...o, challenge: b64u.dec(o.challenge),
    allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) } });
  return api("/api/passkeys/auth/verify", { body: { approval_token: approvalToken, credential: { id: a.id, rawId: b64u.enc(a.rawId), type: a.type,
    response: { clientDataJSON: b64u.enc(a.response.clientDataJSON), authenticatorData: b64u.enc(a.response.authenticatorData),
      signature: b64u.enc(a.response.signature), userHandle: a.response.userHandle ? b64u.enc(a.response.userHandle) : null } } } });
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-User-Id": state.user },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (error ${res.status}).`);
  return data;
}
function toast(text) {
  const t = document.createElement("div");
  t.className = "toast"; t.setAttribute("role", "status"); t.textContent = text;
  document.body.appendChild(t); setTimeout(() => t.remove(), 4000);
}

const DEMO_POLICY = `You may return most items within 30 days of delivery for a full refund to the original payment method.
Items must be unused, in original packaging, with proof of purchase.
Defective items qualify for a 7-day replacement from the date of delivery.
All headphones and speakers carry a 1-year limited warranty.
In-ear earbuds are non-returnable once opened for hygiene reasons.
Customer pays return shipping unless the item arrived defective.`;

function cartFromUrl() {
  const p = new URLSearchParams(location.search).get("cart");
  if (!p) return null;
  try { return JSON.parse(decodeURIComponent(escape(atob(p)))); } catch { return null; }
}

/* =============================================================== HOME */
const QUICK = {
  quick_checkout: ["Pay", "pay", ICON.pay], refund_tracker: ["Returns", "activity", ICON.refund],
  active_purchases: ["Purchases", "activity", ICON.box], budget: ["Budget", "money", ICON.chart],
  bills_reminders: ["Bills", "money", ICON.bell], price_watch: ["Prices", "pay", ICON.tag],
  merchant_qr: ["Counter QR", "business", ICON.qr], invoices: ["Invoices", "business", ICON.doc],
  investments: ["Investing", "money", ICON.invest],
};
const views = {
  async home() {
    const [home, obs, b] = await Promise.all([api("/api/home"), api("/api/obligations"), api("/api/budget")]);
    const used = b.total_budget ? Math.min(1, b.month_spent / b.total_budget) : null;
    view.innerHTML = `
      <section class="hero">
        <div>
          <div class="label">Spent this month</div>
          <div class="big num">${money(b.month_spent)}</div>
          ${used == null ? `<p>Set a budget in Money to see how much is left.</p>` : `
            <p style="margin:6px 0 10px">${money(b.remaining)} left of your ${money(b.total_budget)} budget</p>
            <div class="bar" role="img" aria-label="${Math.round(used * 100)}% of budget used"><span style="width:${used * 100}%"></span></div>`}
          ${(home.alerts || []).slice(0, 2).map((a) => `<div class="alert">${esc(a)}</div>`).join("")}
        </div>
        <div>
          <div class="label">Next payday</div><div style="font-size:1.4rem;font-weight:800">${esc(b.next_payday)}</div>
          <div class="label" style="margin-top:12px">Bills before then</div>
          <div style="font-size:1.4rem;font-weight:800">${money(b.bills_before_payday.reduce((s, x) => s + x.amount, 0))}</div>
        </div>
      </section>
      <h2 style="margin:26px 0 12px">Quick actions</h2>
      <div class="quick">${home.shortcuts.map((s) => QUICK[s] ? `<button data-arm="${esc(s)}" data-go="${QUICK[s][1]}"><span class="ico">${QUICK[s][2]}</span>${QUICK[s][0]}</button>` : "").join("")}</div>
      <p class="small muted">These reorder as ContextIQ learns what you use. ${sys("ai")}</p>
      <div class="grid cols-2" style="margin-top:18px">
        <section class="card"><div class="card-head"><h2>Coming up</h2>${sys("money")}</div>
          ${obs.length ? `<ul class="list">${obs.slice(0, 7).map((o) => `<li><span>${esc(o.title)}</span>
            <span class="num ${o.status === "closing" ? "" : "muted"}">${o.amount ? money(o.amount) + " · " : ""}${o.status === "expired" ? "passed" : Math.round(o.days_left) <= 0 ? "today" : `in ${Math.round(o.days_left)} day${Math.round(o.days_left) === 1 ? "" : "s"}`}</span></li>`).join("")}</ul>`
            : `<p class="muted">Nothing due. Deadlines from purchases and bills show up here.</p>`}
        </section>
        <section class="card"><div class="card-head"><h2>Everything ContextIQ does</h2></div>
          <p class="muted">19 features across payments, your purchase records, money planning, security and AI help — each one shown separately.</p>
          <button class="btn btn-check" data-goto="features">See all features</button>
        </section>
      </div>`;
    view.querySelectorAll("[data-arm]").forEach((b2) => b2.onclick = () => {
      api("/api/feedback", { body: { arm: b2.dataset.arm, reward: 1 } }).catch(() => {});
      go(b2.dataset.go);
    });
    bindGoto();
  },

  /* ============================================================== PAY */
  async pay() {
    const c = state.cart || cartFromUrl() || { merchant: "BrightMart Electronics", seller_id: "brightmart", currency: state.config.currency || "USD",
      items: [{ name: "SoundWave Headphones", unit_price: 249, quantity: 1 }], policy_text: DEMO_POLICY, policy_url: "/demo-store/#policy" };
    state.cart = c;
    const total = c.items.reduce((s, i) => s + i.unit_price * (i.quantity || 1), 0);
    view.innerHTML = `
      <h1>Pay</h1>
      <p class="lede">ContextIQ checks the store's terms, your budget and the payment's safety first. Then you pay with PayPal, and everything is saved to the purchase's record.</p>
      <div class="grid cols-2">
        <section class="card"><div class="card-head"><h2>Your cart · ${esc(c.merchant)}</h2>${sys("payments")}</div>
          <ul class="list">${c.items.map((i) => `<li><span>${esc(i.name)}${(i.quantity || 1) > 1 ? ` × ${i.quantity}` : ""}</span><span class="num">${money(i.unit_price * (i.quantity || 1), c.currency)}</span></li>`).join("")}
            <li><strong>Total</strong><strong class="num">${money(total, c.currency)}</strong></li></ul>
          <div class="row" style="margin-top:14px"><button class="btn btn-check" id="analyze">Check before paying</button>
          <a class="btn btn-quiet" href="/demo-store/">Open the demo store</a></div>
        </section>
        <section class="card" id="analysis"><div class="card-head"><h2>Before you pay</h2>${sys("ai")}</div>
          <p class="muted">Press "Check before paying" to see the return terms, what this does to your budget, and whether anything looks risky.</p></section>
      </div>
      <section class="card" id="paybox" style="margin-top:18px" hidden></section>`;
    $("#analyze").onclick = analyze;
  },

  /* ========================================================== ACTIVITY */
  async activity() {
    const [list, graph] = await Promise.all([api("/api/cases"), api("/api/graph")]);
    if (!state.caseId && list.length) state.caseId = list[0].id;
    view.innerHTML = `
      <h1>Activity</h1>
      <p class="lede">Every purchase has a record ContextIQ keeps up to date. The stamps show who vouches for each fact: PayPal, the other party, or ContextIQ's own reasoning.</p>
      <div class="grid" style="grid-template-columns:minmax(230px,300px) 1fr">
        <div><ul class="case-pick">${list.map((c) => `<li><button data-id="${esc(c.id)}" aria-pressed="${c.id === state.caseId}">
          <strong>${esc(c.title)}</strong><span class="small muted">${esc(c.merchant)}</span>
          <span class="small"><span class="num">${money(c.amount, c.currency)}</span> · ${nice(c.payment_state)}</span></button></li>`).join("")
          || `<li class="muted">No purchases yet. Pay for something and its record appears here.</li>`}</ul>
          <section class="card graph" style="margin-top:14px;padding:16px"><div class="card-head"><h3 style="margin:0">Your connections</h3>${sys("connect")}</div>${graphSvg(graph)}</section>
        </div>
        <section class="card" id="casebox"><p class="muted">Choose a purchase.</p></section>
      </div>`;
    view.querySelectorAll(".case-pick button").forEach((b) => b.onclick = () => { state.caseId = b.dataset.id; views.activity(); });
    if (state.caseId) renderCase(state.caseId);
  },

  /* ============================================================ MONEY */
  async money() {
    const b = await api("/api/budget");
    view.innerHTML = `
      <h1>Money</h1>
      <p class="lede">${esc(b.coverage_note)}</p>
      <div class="grid cols-2">
        <section class="card"><div class="card-head"><h2>Spending this month</h2>${sys("money")}</div>
          <div class="amount num">${money(b.month_spent)}</div>
          ${b.total_budget ? `<p class="muted" style="margin-top:0">of your ${money(b.total_budget)} budget</p>` : ""}
          <table><tbody>${Object.entries(b.by_category).map(([k, v]) => { const lim = b.category_budgets[k]; return `<tr><td>${nice(k)}</td><td class="num">${money(v)}</td>
            <td style="width:38%">${lim ? `<div class="bar ${v > lim ? "over" : ""}"><span style="width:${Math.min(100, v / lim * 100)}%"></span></div><span class="small muted">limit ${money(lim)}</span>` : ""}</td></tr>`; }).join("")}</tbody></table>
          <form id="setb" class="row" style="margin-top:14px;align-items:end"><label class="field" style="flex:1">Monthly budget<input type="number" id="blim" value="${b.total_budget || ""}" min="0" step="50"></label><button class="btn btn-primary">Save budget</button></form>
        </section>
        <section class="card"><div class="card-head"><h2>Can I afford it?</h2>${sys("ai")}</div>
          <form id="wif" class="row" style="align-items:end"><label class="field" style="flex:1">Price<input type="number" id="wamt" value="300" min="0"></label><button class="btn btn-check">Check</button></form>
          <div id="wout" style="margin-top:12px"></div>
          <h3>Bills before payday (${esc(b.next_payday)})</h3>
          ${b.bills_before_payday.length ? `<ul class="list">${b.bills_before_payday.map((x) => `<li><span>${esc(x.title)}</span><span class="num">${money(x.amount)} · ${esc(x.due)}</span></li>`).join("")}</ul>` : `<p class="muted">None.</p>`}
        </section>
        <section class="card"><div class="card-head"><h2>Recurring payments</h2>${sys("ai")}</div>
          ${b.subscriptions.length ? `<ul class="list">${b.subscriptions.map((s) => `<li><span>${esc(s.payee)}<br><span class="small muted">about every ${s.every_days} days · next around ${esc(s.next_expected)}</span></span><span class="num">${money(s.amount)}</span></li>`).join("")}</ul>`
            : `<p class="muted">No recurring payments found yet.</p>`}
        </section>
        <section class="card"><div class="card-head"><h2>Next 30 days</h2>${sys("ai")}</div>
          <div style="font-size:1.6rem;font-weight:800" class="num">${money(b.forecast_30d.p10)} – ${money(b.forecast_30d.p90)}</div>
          <p class="muted">What your everyday spending will probably be. It's a range, not a promise.</p>
        </section>
        <section class="card"><div class="card-head"><h2>Investing</h2>${sys("money")}</div>
          <p class="small muted">Optional. Checks whether money is truly spare before anything else. Education, not advice.</p>
          <form id="invf" class="row" style="align-items:end"><label class="field">Amount<input type="number" id="iamt" value="1000" min="0"></label>
          <label class="field">For how long<select class="input" id="ihz"><option value="1">About a month</option><option value="12" selected>About a year</option><option value="60">5 years or more</option></select></label><button class="btn btn-check">Check</button></form>
          <div id="iout" style="margin-top:12px"></div>
          <h3>Look up a company</h3>
          <form id="rsf" class="row" style="align-items:end"><label class="field">Ticker<input type="text" id="sym" value="IBM" style="text-transform:uppercase;max-width:140px"></label><button class="btn btn-check">Research</button></form>
          <div id="rsout" style="margin-top:10px"></div>
          <h3>How spread out are my investments?</h3>
          <label class="field">One per line: ticker, value, sector<textarea id="hold">ACME, 7000, Technology
INDEXFUND, 3000, Broad market</textarea></label>
          <div class="row" style="margin-top:8px"><button class="btn btn-check" id="divb">Check</button></div><div id="divout" style="margin-top:10px"></div>
        </section>
      </div>`;
    $("#setb").onsubmit = async (e) => { e.preventDefault(); await api("/api/budget", { body: { category: "total", limit: Number($("#blim").value) } }); toast("Budget saved."); views.money(); };
    $("#wif").onsubmit = async (e) => { e.preventDefault(); const r = await api(`/api/whatif?amount=${Number($("#wamt").value)}`);
      $("#wout").innerHTML = `<p class="notice ${esc(r.verdict)}">${esc(r.message)}</p>`; };
    $("#rsf").onsubmit = async (e) => { e.preventDefault();
      const r = await api(`/api/invest/research?symbol=${encodeURIComponent($("#sym").value)}`);
      if (!r.connected) { $("#rsout").innerHTML = `<p class="notice wait">${esc(r.message)}</p>`; return; }
      if (r.error) { $("#rsout").innerHTML = `<p class="notice deny">${esc(r.error)}</p>`; return; }
      const f = r.fundamentals, q = r.quote;
      $("#rsout").innerHTML = `<p><strong>${esc(f.name || r.symbol)}</strong> · ${esc(f.sector || "")} · ${q.found ? `price ${q.price} (${esc(q.change_pct)}, ${esc(q.as_of)})` : "no quote"} ${stamp("verified", "market data")}</p>
        <ul>${r.risk_flags.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        ${r.news.articles.length ? `<p class="small">Recent news (sentiment ${r.news.avg_sentiment}): ${r.news.articles.slice(0, 3).map((a) => esc(a.title)).join(" · ")}</p>` : ""}
        <p class="small muted">${esc(r.reminder)}</p>`; };
    $("#divb").onclick = async () => {
      const holdings = $("#hold").value.split("\n").map((l) => l.split(",").map((x) => x.trim())).filter((p) => p.length >= 2 && p[0])
        .map(([symbol, value, sector]) => ({ symbol, value: Number(value) || 0, sector }));
      const r = await api("/api/invest/diversification", { body: { holdings } });
      $("#divout").innerHTML = `<p class="notice ${r.level === "concentrated" ? "wait" : "ok"}">Your investments are <strong>${esc(r.level)}</strong>.</p>${r.notes.map((n) => `<p class="small">${esc(n)}</p>`).join("")}`;
    };
    $("#invf").onsubmit = async (e) => { e.preventDefault();
      const r = await api("/api/invest", { body: { amount: Number($("#iamt").value), horizon_months: Number($("#ihz").value) } });
      $("#iout").innerHTML = !r.enabled ? `<p class="muted">${esc(r.message)}</p>` : `
        <p class="notice ${r.liquidity.status === "ok" ? "ok" : "wait"}">${esc(r.liquidity.message)}</p>
        <table><thead><tr><th>Option</th><th>Typical result</th><th>Likely range</th><th>Chance of a loss</th></tr></thead><tbody>
        ${r.options.map((o) => `<tr><td>${esc(o.bucket)}</td><td class="num">${money(o.median)}</td><td class="num">${money(o.p10)} – ${money(o.p90)}</td><td class="num">${Math.round(o.chance_of_loss * 100)}%</td></tr>`).join("")}</tbody></table>
        <p class="small muted">${esc(r.disclaimer)}</p>`; };
  },

  /* ========================================================= BUSINESS */
  async business() {
    const merchant = state.role === "merchant" || state.role === "supplier";
    view.innerHTML = `
      <h1>Business</h1>
      <p class="lede">Catch invoice mistakes before money moves, give counter customers a signed itemised bill, and read any payment QR code.</p>
      <div class="grid cols-2">
        <section class="card"><div class="card-head"><h2>Check an invoice</h2>${sys("briefcase")}</div>
          <p class="small muted">One item per line: name, quantity, unit price.</p>
          <label class="field">What you ordered (purchase order)<textarea id="po">Sensor board, 30, 40.00
Wiring harness, 10, 12.50</textarea></label>
          <label class="field" style="margin-top:8px">What they billed (invoice)<textarea id="inv">Sensor board, 30, 42.50
Wiring harness, 10, 12.50
Express handling, 1, 35.00</textarea></label>
          <label class="field" style="margin-top:8px">Message that came with it<input type="text" id="invmsg" value="Please pay today to avoid delays."></label>
          <div class="row" style="margin-top:12px"><button class="btn btn-check" id="chk">Compare</button></div>
          <div id="invout" style="margin-top:12px"></div>
        </section>
        <section class="card"><div class="card-head"><h2>${merchant ? "Counter QR for a customer" : "Pay at a counter"}</h2>${sys("connect")}</div>
          ${merchant ? `<label class="field">Items<textarea id="qritems">USB-C cable, 2, 12.50
Phone case, 1, 19.00</textarea></label><div class="row" style="margin-top:12px"><button class="btn btn-primary" id="mkqr">Create signed QR</button></div><div id="qrout" style="margin-top:12px"></div>`
            : `<p class="muted">Paste or scan any payment code. ContextIQ tells you what it really contains, and opens the bill if it's a signed ContextIQ code.</p>
               <label class="field">Code<textarea id="scanin" placeholder="Paste a QR code's contents"></textarea></label>
               <div class="row" style="margin-top:12px"><button class="btn btn-check" id="scan">Read code</button>
               <button class="btn btn-quiet" id="eg-upi" type="button">Try a UPI example</button><button class="btn btn-quiet" id="eg-emv" type="button">Try a bank QR example</button></div>
               <div id="scanout" style="margin-top:12px"></div>`}
        </section>
      </div>`;
    const parse = (t) => t.split("\n").map((l) => l.split(",").map((x) => x.trim())).filter((p) => p.length >= 3 && p[0])
      .map(([name, q, p]) => ({ name, quantity: Number(q) || 1, unit_price: Number(p) || 0 }));
    $("#chk").onclick = async () => {
      const r = await api("/api/invoice/check", { body: { supplier: "Nova Parts Co", po: { payee: "Nova Parts Co", items: parse($("#po").value) },
        invoice: { payee: "Nova Parts Co", items: parse($("#inv").value) }, text: $("#invmsg").value } });
      $("#invout").innerHTML = `<p class="notice ${esc(r.status)}"><strong>${esc(r.recommendation)}</strong></p>
        <p class="num">Ordered ${money(r.po_total)} · billed ${money(r.invoice_total)} · difference ${money(r.difference)}</p>
        ${r.issues.length ? `<ul>${r.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}
        <p class="small muted">Safety check: ${{ allow: "nothing unusual", step_up: "we'd ask you to confirm it's you", review: "we'd hold this payment for a closer look" }[r.risk.decision]} — ${esc(r.risk.reasons.join("; "))}.</p>`;
    };
    if (merchant) {
      $("#mkqr").onclick = async () => {
        const r = await api("/api/qr/create", { body: { items: parse($("#qritems").value), policy_text: DEMO_POLICY } });
        const qr = qrcode(0, "L"); qr.addData(r.qr_token); qr.make();
        $("#qrout").innerHTML = `<div class="qr">${qr.createSvgTag({ cellSize: 3, margin: 2, scalable: true })}</div>
          <p class="small"><strong>${money(r.amount, r.currency)}</strong> · signed by ${esc(r.merchant)} · works once · expires in ${Math.round(r.expires_in_s / 60)} minutes</p>
          <details><summary class="small">Code text (for the demo, paste it on the customer's screen)</summary><p class="mono">${esc(r.qr_token)}</p></details>`;
      };
    } else {
      $("#eg-upi").onclick = () => { $("#scanin").value = "upi://pay?pa=freshmart@okbank&pn=FreshMart&am=450.00&cu=INR&tn=Groceries"; };
      $("#eg-emv").onclick = () => { $("#scanin").value = "00020101021226300014A0000000041234567890125204541153033565406450.005802IN5909FreshMart6009Bengaluru6304ABCD"; };
      $("#scan").onclick = async () => {
        const raw = $("#scanin").value.trim();
        const info = await api("/api/qr/interpret", { body: { raw } });
        if (info.format === "ContextIQ signed bill") {
          const r = await api("/api/qr/scan", { body: { token: raw } });
          if (!r.ok) { $("#scanout").innerHTML = `<p class="notice deny">Not accepted: ${esc(r.error)}</p>`; return; }
          state.checkout = r;
          $("#scanout").innerHTML = `<p class="notice ok">Signature checked — this bill really is from <strong>${esc(r.verified_merchant)}</strong>.</p>
            <ul class="list">${r.items.map((i) => `<li><span>${esc(i.name)} × ${i.quantity}</span><span class="num">${money(i.unit_price * i.quantity)}</span></li>`).join("")}</ul>
            <div id="qrpay" style="margin-top:12px"></div>`;
          renderPayStep($("#qrpay"));
          return;
        }
        $("#scanout").innerHTML = `<p class="notice ${info.payable_with_paypal ? "ok" : "wait"}"><strong>${esc(info.format)}.</strong> ${esc(info.summary)}</p>
          <table><tbody>${["payee", "amount", "currency", "city", "note"].filter((k) => info[k] != null).map((k) => `<tr><th>${nice(k)}</th><td>${esc(info[k])}</td></tr>`).join("")}
          <tr><th>Item details</th><td>${info.itemised ? "Yes" : "Not included in this code"}</td></tr></tbody></table>`;
      };
    }
  },

  /* ======================================================== ASSISTANT */
  async ask() {
    view.innerHTML = `
      <h1>Assistant</h1>
      <p class="lede">Ask in your own words, or tap the microphone at the top. Answers come from your purchase records and PayPal, and say what's still unknown. ${sys("ai")}</p>
      <div class="chips" style="margin-bottom:16px">${["My headphones stopped working. Can I return them?", "Why does my supplier say payment wasn't received?",
        "Can I afford $300 headphones?", "What subscriptions do I have?", "I have $1000 spare. Should I invest it?",
        "Supplier says urgent: new bank details, wire now"].map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
      <section class="card"><div class="chatlog" id="log" aria-live="polite"><p class="muted">Ask me anything about a payment, a refund, a bill or your budget.</p></div>
      <form id="askf" class="row" style="margin-top:14px"><input type="text" id="q" placeholder="Type your question" style="flex:1" aria-label="Your question"><button class="btn btn-primary">Ask</button></form></section>`;
    view.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => sendChat(b.dataset.q));
    $("#askf").onsubmit = (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) { $("#q").value = ""; sendChat(q); } };
    drawChat();
  },

  /* ============================================================ TRUST */
  async trust() {
    const [m, audit, pk, plugs, con] = await Promise.all([api("/api/metrics"), api("/api/audit"), api("/api/passkeys/status"),
      api("/api/plugins"), api("/api/kg/contradictions")]);
    const f = m.models.fraud || { recall_per_family: {} };
    const fam = f.recall_per_family || {};
    view.innerHTML = `
      <h1>Trust</h1>
      <p class="lede">How ContextIQ keeps you safe, with real measurements. AI can suggest; only the security gateway lets money move.</p>
      <div class="grid cols-2">
        <section class="card"><div class="card-head"><h2>Is this payment request safe?</h2>${sys("security")}</div>
          <form id="rf" class="grid" style="gap:10px">
            <label class="field">Who wants the money<input type="text" id="rpayee" value="Nova Parts Co"></label>
            <label class="field">Amount<input type="number" id="ramt" value="1275"></label>
            <label class="field">Their message<input type="text" id="rtext" value="URGENT: our bank details changed, wire now to avoid penalty"></label>
            <label class="row small"><input type="checkbox" id="rpc" checked> Their bank details changed recently</label>
            <label class="row small"><input type="checkbox" id="rdev"> I'm on a new device</label>
            <div><button class="btn btn-check">Check it</button></div></form>
          <div id="rout" style="margin-top:12px"></div>
        </section>
        <section class="card"><div class="card-head"><h2>How well fraud is caught</h2>${sys("security")}</div>
          <table><thead><tr><th>Kind of attack</th><th>Seen in training</th><th>Caught</th></tr></thead><tbody>
          ${Object.entries(fam).map(([k, v]) => `<tr><td>${nice(k)}</td><td>${v.seen_in_training ? "Yes" : "No — new to it"}</td><td class="num">${k === "invoice_inflation" ? "by invoice check: 100%" : Math.round((v["all three combined"] ?? 0) * 100) + "%"}</td></tr>`).join("")}</tbody></table>
          <p class="small muted">About ${Math.round(((f.false_alarm_rate_on_unseen_normal || {})["all three combined"] || 0) * 100)}% of normal payments get an extra check. Measured on synthetic data.</p>
        </section>
        <section class="card"><div class="card-head"><h2>Speed and cost</h2>${sys("ai")}</div>
          <p>Reused results: <strong class="num">${Math.round(m.cache.hit_rate * 100)}%</strong> · AI words saved: <strong class="num">${m.cache.tokens_saved}</strong> · average response: <strong class="num">${m.api.avg_latency_ms} ms</strong></p>
          <p class="small muted">Reasoning model: ${esc(m.llm.provider || "off — plain-language templates are used")}. Payment status is never served from a cache.</p>
          <div class="row"><button class="btn btn-check" data-cache="on">Cache on</button><button class="btn btn-check" data-cache="off">Cache off</button></div>
        </section>
        <section class="card"><div class="card-head"><h2>Your passkey</h2>${sys("security")}</div>
          <p class="muted">${pk.has_passkey ? "Set up. When we need to check it's you, confirm with your fingerprint, face or device PIN." : "Use your fingerprint, face or device PIN instead of a code when we need to check it's you."}</p>
          <button class="btn btn-primary" id="pkreg">${pk.has_passkey ? "Add another passkey" : "Set up a passkey"}</button><div id="pkout" style="margin-top:8px"></div>
        </section>
        <section class="card"><div class="card-head"><h2>Conflicting facts</h2>${sys("briefcase")}</div>
          ${con.length ? `<ul class="list">${con.slice(0, 6).map((x) => `<li><span>${esc(x.subject)}: ${esc(x.values.join(" vs "))}<br><span class="small muted">${esc(x.sources.join(" vs "))}</span></span><span class="small">${esc(x.trust)}</span></li>`).join("")}</ul>`
            : `<p class="muted">No conflicts. When two sources disagree (say, a seller claims non-payment while PayPal shows it paid), it shows here with which record wins.</p>`}
        </section>
        <section class="card" style="grid-column:1/-1"><div class="card-head"><h2>Connected tools and what they're allowed to do</h2>${sys("security")}</div>
          <table><thead><tr><th>Tool</th><th>Publisher</th><th>Needs</th><th>Limit</th><th>AI can call it</th></tr></thead><tbody>
          ${plugs.map((p) => `<tr><td>${esc(p.id)}<br><span class="small muted">${esc(p.functions.join(", "))}</span></td><td>${esc(p.publisher)}</td><td class="small">${esc(p.scopes.join(", "))}</td><td class="num">${p.rate_limit_per_min}/min</td><td>${p.callable_by_ai ? "Yes" : "<strong>No</strong>"}${p.notes ? `<br><span class="small muted">${esc(p.notes)}</span>` : ""}</td></tr>`).join("")}</tbody></table>
        </section>
        <section class="card"><div class="card-head"><h2>Recent security decisions</h2>${sys("security")}</div>
          ${audit.length ? `<table><tbody>${audit.slice(0, 8).map((a) => `<tr><td>${nice(a.action)}</td><td><span class="notice ${esc(a.verdict)} small" style="padding:2px 8px">${nice(a.verdict)}</span></td><td class="small muted">${esc(a.reasons.join("; "))}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">No decisions yet.</p>`}
        </section>
      </div>`;
    $("#rf").onsubmit = async (e) => { e.preventDefault();
      const r = await api("/api/fraud/score", { body: { payee: $("#rpayee").value, amount: Number($("#ramt").value), text: $("#rtext").value,
        payee_changed_recently: $("#rpc").checked, new_device: $("#rdev").checked } });
      const head = { allow: "Looks normal", step_up: "Be careful — we'd ask you to confirm it's you", review: "Likely a scam — we'd hold this payment" }[r.decision];
      $("#rout").innerHTML = `<p class="notice ${esc(r.decision)}"><strong>${esc(head)}</strong></p>
        <ul>${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="small muted">${esc(r.note)}</p>`; };
    view.querySelectorAll("[data-cache]").forEach((b) => b.onclick = async () => { await api(`/api/cache/${b.dataset.cache}`, { method: "POST" }); views.trust(); });
    $("#pkreg").onclick = async () => {
      if (!window.PublicKeyCredential) { $("#pkout").innerHTML = `<p class="notice wait small">This browser doesn't support passkeys.</p>`; return; }
      try { const r = await passkeyRegister(); $("#pkout").innerHTML = `<p class="notice ok small">${esc(r.message)}</p>`; }
      catch (e) { $("#pkout").innerHTML = `<p class="notice deny small">${esc(e.message)}</p>`; }
    };
  },

  /* ========================================================= FEATURES */
  async features() {
    const fs = await api("/api/features");
    view.innerHTML = `
      <h1>All features</h1>
      <p class="lede">The 18 core features plus optional investing. Each one has its own place in the app; the coloured tag shows which part of ContextIQ runs it.</p>
      <section class="card" style="margin-bottom:18px"><div class="grid cols-2">
        <div><h3 style="margin-top:0">What the buttons mean</h3><div class="legend">
          <div><button class="btn btn-primary" tabindex="-1">Continue</button><span class="small">Safe next step</span></div>
          <div><button class="btn btn-check" tabindex="-1">Check</button><span class="small">Looks things up — changes nothing</span></div>
          <div><button class="btn btn-money" tabindex="-1">${ICON.lock}Complete payment</button><span class="small">Moves money — always needs your approval</span></div>
          <div><button class="btn btn-danger" tabindex="-1">${ICON.lock}Issue refund</button><span class="small">Sends money back — can't be undone</span></div>
          <div><span class="small"><strong>PayPal's own button</strong> appears only at the payment step, loaded from PayPal.</span></div></div></div>
        <div><h3 style="margin-top:0">The parts of ContextIQ</h3><div class="legend">
          <div>${sys("payments")}<span class="small">Talking to PayPal</span></div><div>${sys("briefcase")}<span class="small">Purchase records and evidence</span></div>
          <div>${sys("ai")}<span class="small">Learning and reasoning</span></div><div>${sys("money")}<span class="small">Budgets, bills, investing</span></div>
          <div>${sys("security")}<span class="small">Fraud checks and approvals</span></div><div>${sys("connect")}<span class="small">Buyers, sellers and QR codes</span></div></div></div>
      </div></section>
      <div class="grid cols-3">${fs.map((f) => `<section class="card feature"><div class="row" style="justify-content:space-between"><span class="n">Feature ${f.n}</span>${sys(f.system)}</div>
        <h3>${esc(f.name)}</h3><p class="small" style="margin:0">${esc(f.what)}</p><span class="status">Status: ${esc(f.status)}</span>
        <div><button class="btn btn-quiet" data-goto="${esc(f.where)}">Open</button></div></section>`).join("")}</div>`;
    bindGoto();
  },
};

/* ================================================================ PAY FLOW */
async function analyze() {
  const box = $("#analysis");
  box.innerHTML = `<div class="card-head"><h2>Before you pay</h2>${sys("ai")}</div><p class="muted">Reading the store's terms and checking your budget…</p>`;
  const total = state.cart.items.reduce((s, i) => s + i.unit_price * (i.quantity || 1), 0);
  const [a, acct] = await Promise.all([api("/api/cart/analyze", { body: state.cart }),
    api("/api/accounts/classify", { body: { payee: state.cart.merchant, description: state.cart.items.map((i) => i.name).join(", "), amount: total } })]);
  const p = a.policy;
  const price = a.prices.find((x) => x.lowest_seen != null);
  box.innerHTML = `<div class="card-head"><h2>Before you pay</h2>${sys("ai")}</div>
    ${p ? `<h3>Store terms ${stamp("claimed", "the store")}</h3><ul>${p.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      ${p.unknown.length ? `<p class="small muted">The policy doesn't say: ${p.unknown.map(nice).join(", ")}.</p>` : ""}
      ${p.injection_flags.length ? `<p class="notice deny small">This page contained hidden instructions aimed at AI assistants. ContextIQ ignored them.</p>` : ""}` : ""}
    <h3>Your budget ${stamp("inferred", "ContextIQ")}</h3><p class="notice ${esc(a.budget.verdict)}">${esc(a.budget.message)}</p>
    ${price ? `<p class="small">Price seen ${price.observations} times; lowest ${money(price.lowest_seen)}${price.is_lowest_seen ? " — this is the lowest so far." : "."}</p>` : ""}
    <h3>Personal or business?</h3><div id="acct"></div>
    <p class="small muted">Safety check: ${{ allow: "nothing unusual", step_up: "we'll ask you to confirm it's you", review: "this payment would be held for a closer look" }[a.risk.decision]}.</p>`;
  renderAccount(acct);
  const pay = $("#paybox");
  pay.hidden = false;
  pay.innerHTML = `<div class="card-head"><h2>Pay with PayPal</h2>${sys("payments")}</div>
    <p class="muted">ContextIQ saves exactly what you're agreeing to (a fingerprint of the items, price and seller), then hands over to PayPal. Nothing is charged until you approve.</p>
    <div id="paystep"></div>`;
  renderPayEntry($("#paystep"));
}

function renderAccount(acct) {
  const el = $("#acct");
  if (!acct.needs_confirmation) { el.innerHTML = `<p class="small">Filed as <strong>${nice(acct.purpose)}</strong>. ${esc(acct.why)}</p>`; return; }
  el.innerHTML = `<p class="small">${esc(acct.question)} <span class="muted">(my guess: ${nice(acct.purpose)})</span></p>
    <div class="row"><button class="btn btn-check" data-p="personal">Personal</button><button class="btn btn-check" data-p="business">Business</button></div>`;
  el.querySelectorAll("[data-p]").forEach((b) => b.onclick = async () => {
    const r = await api("/api/accounts/remember", { body: { payee: state.cart.merchant, purpose: b.dataset.p } });
    state.cart.purpose = b.dataset.p;
    el.innerHTML = `<p class="small">${esc(r.message)}</p>`;
  });
}

function renderPayEntry(el) {
  if (state.config.paypal_env !== "mock" && state.config.paypal_client_id) {
    el.innerHTML = `<div id="pp-buttons" style="max-width:360px"></div><div id="payresult" style="margin-top:12px"></div>`;
    loadPayPalSdk().then(() => {
      window.paypal.Buttons({
        style: { layout: "vertical", shape: "pill", label: "pay" },
        createOrder: async () => {
          const r = await api("/api/checkout", { body: state.cart });
          state.checkout = r; state.caseId = r.case_id;
          sessionStorage.setItem("ciq-checkout", JSON.stringify(r));
          return r.order.order_id;
        },
        onApprove: async () => { await completePayment(); },
        onError: (err) => { $("#payresult").innerHTML = `<p class="notice deny">PayPal couldn't start the payment: ${esc(err?.message || err)}</p>`; },
      }).render("#pp-buttons");
    }).catch(() => { el.innerHTML = `<p class="notice deny">Couldn't load PayPal's button. Check your internet connection and Client ID.</p>`; });
    return;
  }
  el.innerHTML = `<button class="btn btn-test-paypal" id="startpay">Pay with PayPal (offline test mode)</button>
    <p class="small muted">Test mode: PayPal is simulated on this computer. Set PAYPAL_ENV=sandbox to show PayPal's real button.</p>
    <div id="paystep2"></div>`;
  $("#startpay").onclick = async () => {
    const r = await api("/api/checkout", { body: state.cart });
    state.checkout = r; state.caseId = r.case_id;
    $("#startpay").disabled = true;
    renderPayStep($("#paystep2"));
  };
}

let sdkPromise = null;
function loadPayPalSdk() {
  if (window.paypal) return Promise.resolve();
  sdkPromise ||= new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(state.config.paypal_client_id)}&currency=${encodeURIComponent(state.config.currency || "USD")}&intent=capture`;
    s.onload = res; s.onerror = rej; document.head.appendChild(s);
  });
  return sdkPromise;
}

function renderPayStep(el) {
  const co = state.checkout;
  const mock = state.config.paypal_env === "mock";
  el.innerHTML = `<p class="small">Saved your agreement ${stamp("verified", "ContextIQ")} and created PayPal order <span class="num">${esc(co.order.order_id)}</span>.</p>
    <div class="row">${mock ? `<button class="btn btn-check" id="approve">1. Approve on PayPal (test)</button>` : `<a class="btn btn-check" href="${esc(co.order.approve_url)}" target="_blank" rel="noopener">1. Approve on PayPal</a>`}
    ${moneyBtn("complete", "2. Complete payment")}</div>
    ${mock ? `<label class="row small" style="margin-top:10px"><input type="checkbox" id="drop"> Simulate the internet dropping right after PayPal takes the money</label>` : ""}
    <div id="payresult" style="margin-top:12px"></div>`;
  if (mock) $("#approve").onclick = async () => { await api(`/api/cases/${co.case_id}/approve-mock`, { method: "POST" }); toast("Approved on PayPal (test mode)."); };
  $("#complete").onclick = () => completePayment();
}

async function completePayment(code) {
  const co = state.checkout;
  const drop = $("#drop")?.checked;
  const path = `/api/cases/${co.case_id}/${drop ? "simulate-drop" : "capture"}`;
  const r = await api(path, { body: { approval_token: co.approval_token, step_up_code: code || null } });
  const out = $("#payresult");
  if (r.gateway === "step_up") {
    $("#stepup-why").textContent = "We need to make sure it's you: " + r.reasons.join(", ") + ".";
    $("#stepup-code").textContent = r.step_up_code_demo;
    $("#stepup-input").value = "";
    $("#stepup-ok").innerHTML = `${ICON.lock}Confirm payment`;
    const dlg = $("#stepup");
    const pk = await api("/api/passkeys/status").catch(() => ({}));
    $("#stepup-pk").hidden = !pk.has_passkey;
    $("#stepup-pk").onclick = async () => {
      try { await passkeyConfirm(co.approval_token); dlg.close(); completePayment(); }
      catch (e) { toast("Passkey didn't work: " + e.message + " — use the code instead."); }
    };
    dlg.showModal();
    $("#stepup-ok").onclick = () => { dlg.close(); completePayment($("#stepup-input").value.trim()); };
    $("#stepup-cancel").onclick = () => dlg.close();
    return;
  }
  if (!r.ok) { out.innerHTML = `<p class="notice deny">${esc(r.error || (r.reasons || []).join("; "))}</p>`; return; }
  sessionStorage.removeItem("ciq-checkout");
  out.innerHTML = `<p class="notice ok"><strong>Paid.</strong> PayPal reference <span class="num">${esc(r.capture_id)}</span> ${stamp("verified", "PayPal")}</p>
    ${r.healed ? `<p class="small">Your connection dropped during payment. Before trying again, ContextIQ asked PayPal what had happened:</p><ol class="small">${r.trace.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>
      ${r.paypal_captures_for_order != null ? `<p><strong>Times you were charged: ${r.paypal_captures_for_order}</strong></p>` : ""}` : ""}
    <button class="btn btn-primary" id="seecase">See the purchase record</button>`;
  $("#seecase").onclick = () => go("activity");
  if (state.config.paypal_env === "mock") api("/api/mock/deliver-webhooks", { method: "POST" }).catch(() => {});
}

/* ============================================================ CASE VIEW */
async function renderCase(id) {
  const box = $("#casebox");
  let v;
  try { v = await api(`/api/cases/${id}`); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const c = v.case, seller = v.role === "seller";
  const by = { paypal_api: "PayPal", paypal_webhook: "PayPal", contextiq: "ContextIQ", merchant_page: "the store", contextiq_qr: "signed QR",
    supplier: "the supplier", buyer: "the buyer", seller: "the seller", context_model: "ContextIQ", refund_expert: "ContextIQ", resolution_expert: "ContextIQ" };
  box.innerHTML = `
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div><h2 style="margin:0">${esc(c.title)}</h2><p class="small muted" style="margin:2px 0 0">${esc(c.merchant)} · ${nice(c.channel)} · ${nice(c.purpose)} · you're the ${esc(v.role)}</p></div>
      <div style="text-align:right"><div class="amount num">${money(c.amount, c.currency)}</div><span class="pill ${esc(c.payment_state)}">${nice(c.payment_state)}</span></div></div>
    <div class="grid cols-2" style="margin-top:8px">
      <div><h3>Progress ${sys("briefcase")}</h3><ul class="check">${(v.checklist || []).map((i) => `<li class="${i.done ? "done" : ""}"><span class="box">${i.done ? ICON.check : ""}</span>${esc(i.item)}</li>`).join("")}</ul>
        <p class="small muted">Ticks only when PayPal or a signed record confirms it — never on someone's word.</p></div>
      <div><h3>Deadlines ${sys("money")}</h3>${v.obligations.length ? `<ul class="list">${v.obligations.map((o) => `<li><span>${esc(o.title.split(" — ")[0])}</span><span class="num small">${esc(o.due_at.slice(0, 10))} · ${nice(o.status)}</span></li>`).join("")}</ul>` : `<p class="muted small">None.</p>`}</div>
    </div>
    <h3>Evidence</h3>
    <ul class="ledger">${v.evidence.map((e) => `<li><div class="stampcol">${stamp(e.provenance, by[e.source] || e.source)}</div>
      <div><div class="what">${esc(e.summary)}</div><div class="meta">from ${esc(by[e.source] || nice(e.source))}${e.cites.length ? ` · based on ${e.cites.length} record(s)` : ""}</div></div></li>`).join("")}</ul>
    ${v.agreement ? `<p class="small muted">Agreement fingerprint <span class="num">${esc(v.agreement.hash.slice(0, 16))}…</span> — any later change to the price, items or seller wouldn't match it.</p>` : ""}
    <details><summary class="small">Full timeline (${v.events.length} events)</summary><table><tbody>${v.events.map((e) => `<tr><td class="num small">${esc(e.at.slice(5, 16).replace("T", " "))}</td><td>${nice(e.type)}</td><td class="small muted">${nice(e.source)}</td></tr>`).join("")}</tbody></table></details>
    <div class="row" style="margin-top:16px">
      ${!seller ? `<button class="btn btn-check" id="deliv">Mark as delivered</button><button class="btn btn-check" id="elig">Can I return this?</button>` : ""}
      <button class="btn btn-check" id="inv">Check payment with PayPal</button>
      ${seller && ["captured", "partially_refunded"].includes(c.payment_state) ? moneyBtn("refund", "Approve and issue refund", "btn-danger") : ""}
    </div>
    <div id="caseout" style="margin-top:12px"></div>
    <h3 style="margin-top:22px">Both sides' view ${sys("connect")}</h3>
    <p class="small muted">If you and the other side disagree, record what you say. ContextIQ lines it up against the verified records instead of picking a side.</p>
    <div class="row"><button class="btn btn-check" data-claim="delivered:true">It arrived</button><button class="btn btn-check" data-claim="delivered:false">It didn't arrive</button>
      <button class="btn btn-check" data-claim="paid:true">Payment received</button><button class="btn btn-check" data-claim="paid:false">Payment not received</button>
      <button class="btn btn-check" data-claim="item_ok:false">Item faulty</button></div>
    <div id="cmp" style="margin-top:10px"></div>
    ${!seller && v.role === "buyer" ? `<h3 style="margin-top:22px">Agent-to-agent check ${sys("connect")}</h3>
      <p class="small muted">Your ContextIQ agent and the seller's agent exchange signed messages, each sharing only what it's allowed to (never your budget or other purchases), and compare the order with the invoice.</p>
      <div class="row"><button class="btn btn-check" id="a2a">Connect with the seller's agent</button><button class="btn btn-quiet" id="a2a-tamper">Test: tamper with a message</button></div>
      <div id="a2aout" style="margin-top:10px"></div>` : ""}`;
  const out = $("#caseout");
  $("#deliv") && ($("#deliv").onclick = async () => { await api(`/api/cases/${id}/delivered?days_ago=2`, { method: "POST" }); toast("Delivery saved. Return deadlines now count from the delivery date."); renderCase(id); });
  $("#elig") && ($("#elig").onclick = async () => {
    const r = await api(`/api/cases/${id}/refund-eligibility?issue=${encodeURIComponent("it stopped working")}`);
    const ch = r.decision.choice;
    const hasSwap = r.options.some((o) => o.name === "request_replacement" && o.permitted);
    const hasWarranty = r.options.some((o) => o.name === "warranty_claim" && o.permitted);
    const hasDispute = r.options.some((o) => o.name === "escalate_to_paypal_protection" && o.permitted) || !r.eligible;

    let actions = `<div class="row" style="margin-top:12px;gap:8px">`;
    if (hasSwap) actions += `<button class="btn btn-primary" id="cswap">Initiate Free Swap / Replacement</button>`;
    if (hasWarranty) actions += `<button class="btn btn-check" id="cwarranty">Claim Warranty Repair</button>`;
    if (hasDispute) actions += `<button class="btn btn-danger" id="cdispute">Escalate to PayPal Dispute</button>`;
    actions += `</div>`;

    out.innerHTML = `<p class="notice ${r.eligible ? "ok" : "wait"}">${esc(r.reason)}</p>
      ${ch ? `<p>Best option: <strong>${nice(ch.name)}</strong> — ${esc(ch.explanation.toLowerCase())}. <span class="small muted">How sure: ${esc(r.decision.confidence)}.${r.uncertainty.missing.length ? ` Still missing: ${r.uncertainty.missing.map(nice).join(", ")}.` : ""}</span></p>` : ""}
      <table><thead><tr><th>Option</th><th>Score</th><th>Allowed by the store's terms</th></tr></thead><tbody>${r.decision.ranked.map((o) => `<tr><td>${nice(o.name)}</td><td class="num">${o.score == null ? "—" : o.score.toFixed(2)}</td><td>${o.permitted ? "Yes" : "No"}</td></tr>`).join("")}</tbody></table>
      ${actions}`;

    $("#cswap") && ($("#cswap").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "request_replacement", issue: "faulty unit swap" } });
      out.innerHTML = rr.ok ? `<p class="notice ok">Free replacement swap registered in briefcase. Supplier alerted.</p>` : `<p class="notice deny">${esc(rr.error)}</p>`;
      renderCase(id);
    });
    $("#cwarranty") && ($("#cwarranty").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "warranty_claim", issue: "hardware defect under warranty" } });
      out.innerHTML = rr.ok ? `<p class="notice ok">Warranty claim anchored in briefcase.</p>` : `<p class="notice deny">${esc(rr.error)}</p>`;
      renderCase(id);
    });
    $("#cdispute") && ($("#cdispute").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "escalate_to_paypal_protection", issue: "unresolved delivery issue" } });
      out.innerHTML = rr.ok ? `<p class="notice ok">Escalated to PayPal Purchase Protection.</p>` : `<p class="notice deny">${esc(rr.error)}</p>`;
      renderCase(id);
    });
  });
  $("#inv").onclick = async () => {
    const r = await api(`/api/cases/${id}/investigate`, { method: "POST" });
    out.innerHTML = `<p class="notice ${r.verdict === "paid" ? "ok" : "wait"}">${esc(r.explanation.join(" "))}</p><p>${esc(r.next_step)}</p>`;
  };
  $("#refund") && ($("#refund").onclick = async () => {
    const { approval_token } = await api(`/api/cases/${id}/refund/approve`, { method: "POST" });
    let r = await api(`/api/cases/${id}/refund`, { body: { approval_token, reason: "defective item" } });
    if (r.gateway === "step_up") {
      const code = prompt(`We need to make sure it's you: ${r.reasons.join(", ")}.\nDemo code: ${r.step_up_code_demo}`);
      if (!code) return;
      r = await api(`/api/cases/${id}/refund`, { body: { approval_token, step_up_code: code, reason: "defective item" } });
    }
    out.innerHTML = r.ok ? `<p class="notice ok">Refund sent through PayPal ${stamp("verified", "PayPal")}</p>` : `<p class="notice deny">${esc(JSON.stringify(r.error || r.reasons))}</p>`;
    renderCase(id);
  });
  const drawCmp = async () => {
    const r = await api(`/api/cases/${id}/compare`);
    const yn = (x) => x == null ? "—" : x ? "Yes" : "No";
    $("#cmp").innerHTML = `<table><thead><tr><th>Question</th><th>Buyer says</th><th>Seller says</th><th>Records show</th><th>Result</th></tr></thead><tbody>
      ${r.points.map((p) => `<tr><td>${esc(p.topic)}</td><td>${yn(p.buyer_says)}</td><td>${yn(p.seller_says)}</td><td>${yn(p.verified)}</td><td>${esc(p.status)}</td></tr>`).join("")}</tbody></table>
      <p class="small">${esc(r.recommendation)}</p>`;
  };
  view.querySelectorAll("[data-claim]").forEach((b) => b.onclick = async () => {
    const [topic, val] = b.dataset.claim.split(":");
    await api(`/api/cases/${id}/claims`, { body: { topic, value: val === "true" } });
    toast("Saved as your claim."); drawCmp();
  });
  drawCmp();
  const a2aRun = async (tamper) => {
    const r = await api("/api/a2a/sessions", { body: { case_id: id, tamper } });
    if (r.error) { $("#a2aout").innerHTML = `<p class="notice wait">${esc(r.error)}</p>`; return; }
    $("#a2aout").innerHTML = `<table><thead><tr><th>Message</th><th>From → to</th><th>Shared fields</th><th>Signature</th></tr></thead><tbody>
      ${r.transcript.map((t) => `<tr><td>${esc(t.type)}</td><td>${esc(t.from)} → ${esc(t.to)}</td><td class="small">${esc(t.fields.join(", "))}</td>
        <td>${t.verified ? stamp("verified", "signature check") : `<span class="notice deny small" style="padding:2px 8px">rejected: ${esc(t.rejected_because)}</span>`}</td></tr>`).join("")}</tbody></table>
      ${r.ok ? `<p class="notice ${r.comparison.match ? "ok" : "wait"}">${r.comparison.match ? "Both agents agree: the order and the invoice match." : "The agents found differences: " + esc(r.comparison.issues.join("; "))}</p>
        <div class="row"><button class="btn btn-check" id="a2async">Tell the seller's agent about the payment</button></div><div id="a2asyncout"></div>`
        : `<p class="notice deny">The handshake stopped: a message failed its signature check, so nothing from it was used.</p>`}`;
    $("#a2async") && ($("#a2async").onclick = async () => {
      const s2 = await api(`/api/a2a/sessions/${r.session}/sync`, { method: "POST" });
      $("#a2asyncout").innerHTML = `<p class="small">Agents: <strong>${nice(s2.sync_state)}</strong> · payment: <strong>${nice(s2.payment_state)}</strong> (tracked separately — a failed sync never changes the payment).</p>`;
    });
  };
  $("#a2a") && ($("#a2a").onclick = () => a2aRun(null));
  $("#a2a-tamper") && ($("#a2a-tamper").onclick = () => a2aRun("change_amount"));
}

function graphSvg(g) {
  const nodes = g.nodes.slice(0, 18);
  if (nodes.length <= 1) return `<p class="small muted">Your purchases, sellers and deadlines will be mapped here.</p>`;
  const W = 280, H = 260, cx = W / 2, cy = H / 2;
  const others = nodes.filter((n) => n.type !== "you");
  const pos = { [nodes[0].id]: [cx, cy] };
  others.forEach((n, i) => {
    const ring = n.type === "purchase" ? 70 : 115, a = (2 * Math.PI * i) / others.length;
    pos[n.id] = [cx + ring * Math.cos(a), cy + ring * Math.sin(a)];
  });
  const col = { you: "#0b2e6f", purchase: "#1f6feb", merchant: "#a16207", business: "#a16207", person: "#a16207", deadline: "#15803d" };
  const lines = g.edges.filter((e) => pos[e.from] && pos[e.to]).map((e) => `<line x1="${pos[e.from][0]}" y1="${pos[e.from][1]}" x2="${pos[e.to][0]}" y2="${pos[e.to][1]}" stroke="#d3d9e3"/>`).join("");
  const dots = nodes.map((n) => `<g><title>${esc(n.label)}</title><circle cx="${pos[n.id][0]}" cy="${pos[n.id][1]}" r="${n.type === "you" ? 11 : 7}" fill="${col[n.type] || "#55627d"}"/></g>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of your purchases, sellers and deadlines">${lines}${dots}</svg>
    <p class="small muted" style="margin:4px 0 0"><span style="color:#1f6feb">●</span> purchases <span style="color:#a16207">●</span> sellers <span style="color:#15803d">●</span> deadlines</p>`;
}

/* ============================================================ ASSISTANT */
async function sendChat(q, speak = false) {
  if (location.hash !== "#ask" && !$("#log")) await go("ask");
  state.chat.push({ you: true, text: q }); drawChat();
  try {
    const r = await api("/api/chat", { body: { message: q } });
    state.chat.push({ text: r.answer, r });
    if (r.case_id) state.caseId = r.case_id;
    if (speak) say(r.answer);
  } catch (e) { state.chat.push({ text: e.message }); }
  drawChat();
}
function drawChat() {
  const log = $("#log");
  if (!log || !state.chat.length) return;
  log.innerHTML = state.chat.map((m) => m.you ? `<div class="msg you">${esc(m.text)}</div>` : `<div class="msg ciq">${esc(m.text)}
    ${m.r ? `<div class="trace">${sys("ai")} <span>About ${esc(m.r.topic)} · experts: ${m.r.experts.map(nice).join(", ")} · confidence ${esc(m.r.reasoning?.level || "")} · ${m.r.latency_ms} ms${m.r.llm_tokens ? ` · ${m.r.llm_tokens} AI tokens` : ""}</span></div>
      ${m.r.evidence_rounds ? `<div class="trace">Went back for more evidence ${m.r.evidence_rounds} time${m.r.evidence_rounds > 1 ? "s" : ""}.</div>` : ""}
      ${(m.r.resolutions || []).map((x) => `<div class="trace">${esc(x)}</div>`).join("")}
      ${m.r.reasoning?.unknowns?.length ? `<div class="trace">Still unknown: ${m.r.reasoning.unknowns.map(nice).join(", ")}</div>` : ""}
      ${m.r.proposal ? `<div class="row" style="margin-top:8px"><button class="btn btn-primary" data-open-case="${esc(m.r.proposal.case_id)}">Review and confirm</button></div>` : ""}` : ""}</div>`).join("");
  log.querySelectorAll("[data-open-case]").forEach((b) => b.onclick = () => { state.caseId = b.dataset.openCase; go("activity"); });
  log.scrollTop = log.scrollHeight;
}

/* ================================================================ VOICE */
function say(text) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = navigator.language || "en-US";
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function setupVoice() {
  const btn = $("#mic");
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { btn.title = "Voice needs Chrome, Edge or Safari"; btn.onclick = () => toast("Voice isn't supported in this browser. Try Chrome, Edge or Safari."); return; }
  const rec = new SR();
  rec.lang = navigator.language || "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
  rec.onresult = async (e) => {
    const text = e.results[0][0].transcript;
    if (/\b(pay|send|transfer|approve|confirm)\b/i.test(text) && !/\b(did|was|is|status|can i|should)\b/i.test(text)) {
      const msg = "For your safety, I can't pay, send or approve anything by voice. Please confirm it on screen.";
      toast(msg); say(msg); return;
    }
    await go("ask"); sendChat(text, true);
  };
  rec.onend = () => btn.setAttribute("aria-pressed", "false");
  rec.onerror = () => { btn.setAttribute("aria-pressed", "false"); toast("I didn't catch that. Tap the microphone and try again."); };
  btn.onclick = () => { btn.setAttribute("aria-pressed", "true"); try { rec.start(); } catch { rec.stop(); } };
}

/* ================================================================ SHELL */
function bindGoto() { view.querySelectorAll("[data-goto]").forEach((b) => b.onclick = () => go(b.dataset.goto)); }
async function go(name) {
  if (name === "cases") name = "activity";
  if (name === "shop") name = "pay";
  document.querySelectorAll(".tabs [data-view]").forEach((b) => b.removeAttribute("aria-current"));
  document.querySelector(`.tabs [data-view="${name}"]`)?.setAttribute("aria-current", "page");
  history.replaceState(null, "", `#${name}`);
  try { await views[name](); } catch (e) { view.innerHTML = `<h1>That didn't load</h1><p class="notice deny">${esc(e.message)}</p><p class="muted">Check that ContextIQ is running, then reload the page.</p>`; }
  view.focus({ preventScroll: true });
}

(async function init() {
  state.config = await api("/api/config");
  const users = await api("/api/users");
  const sel = $("#who");
  sel.innerHTML = users.map((u) => `<option value="${esc(u.id)}">${esc(u.role === "shopper" ? u.name : `${u.business_name || u.name} (${u.role})`)}</option>`).join("");
  const setUser = (id) => {
    const u = users.find((x) => x.id === id) || users[0];
    state.user = u.id; state.role = u.role; sel.value = u.id; localStorage.setItem("ciq-user", u.id);
  };
  setUser(state.user);
  sel.onchange = () => { setUser(sel.value); state.chat = []; state.caseId = null; go("home"); };
  const env = $("#env");
  if (state.config.paypal_env === "mock") { env.hidden = false; env.textContent = "Offline test mode — PayPal is simulated on this computer. No real or sandbox money moves."; }
  else if (state.config.paypal_env === "sandbox") { env.hidden = false; env.textContent = "PayPal sandbox — test accounts and test money only."; }
  document.querySelectorAll(".tabs [data-view]").forEach((b) => b.onclick = () => go(b.dataset.view));
  const rstBtn = $("#demo-reset-btn");
  if (rstBtn && !state.config.reset_allowed) rstBtn.hidden = true;
  if (rstBtn && state.config.reset_allowed) {
    rstBtn.onclick = async () => {
      if (!confirm("Reset all carts, transactions, and notices to a fresh demo baseline?")) return;
      rstBtn.disabled = true;
      rstBtn.textContent = "Resetting...";
      try {
        await api("/api/reset", { method: "POST" });
        rstBtn.textContent = "✓ Reset Done";
        setTimeout(() => { rstBtn.textContent = "↺ Reset Demo"; rstBtn.disabled = false; }, 2000);
        const hash = location.hash.slice(1);
        go(views[hash] ? hash : "home");
      } catch (err) {
        alert("Reset failed: " + err.message);
        rstBtn.textContent = "↺ Reset Demo";
        rstBtn.disabled = false;
      }
    };
  }
  setupVoice();
  const qs = new URLSearchParams(location.search);
  if (qs.get("approved")) {
    state.caseId = qs.get("approved");
    state.checkout = JSON.parse(sessionStorage.getItem("ciq-checkout") || "null");
    if (state.checkout) {
      view.innerHTML = `<h1>Approved on PayPal</h1><p class="lede">One step left. ContextIQ checks your approval and the security rules, then completes the payment.</p><section class="card" id="finish"></section>`;
      renderPayStep($("#finish")); return;
    }
  }
  const hash = location.hash.slice(1);
  go(cartFromUrl() ? "pay" : views[hash] ? hash : "home");
})();
