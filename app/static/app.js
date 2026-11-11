"use strict";
/* ContextIQ — the web app people use. It tells; it doesn't ask.
   Internals (experts, models, signatures, audit) live on the separate judges' console at /console. */
const $ = (s, el = document) => el.querySelector(s);
const app = $("#app");
const store = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } } };
const S = { user: store.get("ciq-user") === "brightmart" ? "brightmart" : "alex", config: {}, profile: null, account: sessionStorage.getItem("ciq-account") || null, pos: null,
  chat: [], cart: null, checkout: null, home: null, cards: [], tab: "home" };
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SYM = { USD: "$", INR: "₹", EUR: "€", GBP: "£" };
const money = (n, cur = S.config.currency || "USD", dp = 2) => n == null ? "—" :
  `${n < 0 ? "-" : ""}${SYM[cur] || cur + " "}${Math.abs(Number(n)).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
const cap = (s) => String(s || "").charAt(0).toUpperCase() + String(s || "").slice(1);
const I = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
  pay: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18M7 15h4"/></svg>',
  activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12h4l3 7 4-14 3 7h4"/></svg>',
  ask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  swap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M7 7h12l-3-3M17 17H5l3 3"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4"/></svg>',
  repeat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 12a8 8 0 0 1 14-5l2 2M20 12a8 8 0 0 1-14 5l-2-2M20 4v5h-5M4 20v-5h5"/></svg>',
  piggy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 11a7 6 0 0 1 13-3h2v4l-1 1v3h-3l-1 2h-3l-1-2H7l-2-2z"/><circle cx="15" cy="10" r=".6" fill="currentColor"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></svg>',
  plane: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M2 13l20-8-6 16-4-6z M12 15l4-6"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 7l9-4 9 4v10l-9 4-9-4z M3 7l9 4 9-4M12 11v10"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 2h8l5 5v15H6z M14 2v5h5M9 13h7M9 17h7"/></svg>',
  pin: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>',
  tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 12V3h9l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
};
I.qr = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 17v4h-3M17 20h-3"/></svg>';
I.bolt = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>';
I.spark = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z"/></svg>';
I.invest = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg>';
I.calendar = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>';
I.cart = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h2l2.5 11h11L21 7H6.5"/><circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/></svg>';
I.back = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>';
function goBack() { if (S.prevTab && S.prevTab !== S.tab && views[S.prevTab]) go(S.prevTab); else go("home"); }
const backBtnHtml = (target = "") => `<button class="btn-back" onclick="${target ? `go('${target}')` : "goBack()"}">${I.back} Back</button>`;
$("#mic").innerHTML = I.mic; $("#bell").insertAdjacentHTML("afterbegin", I.bell);

async function api(path, opts = {}) {
  const res = await fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-User-Id": S.user }, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (error ${res.status}).`);
  return data;
}
function toast(text, title = "", kind = "", onClick = null, ms = 5000) {
  const t = document.createElement("div"); t.className = `toast ${kind}`; t.setAttribute("role", "status");
  t.innerHTML = `${title ? `<b>${esc(title)}</b>` : ""}${esc(text)}`;
  t.onclick = () => { onClick?.(); t.remove(); };
  $("#toasts").appendChild(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 320); }, ms);
}
function countUp(el, to, fmt) {
  if (!el) return;
  if (RM) { el.textContent = fmt(to); return; }
  const t0 = performance.now(), d = 1100;
  const step = (t) => { const k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 3); el.textContent = fmt(to * e); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
const later = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));
const wait = (ms) => new Promise((r) => setTimeout(r, RM ? 0 : ms));
const fmtDate = (d) => { const x = new Date(d); return x.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(x.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}) }); };
/* ------------------------------------------------------------------ visuals */
function ringSvg(frac, cls = "fill", size = 132, stroke = 12) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return `<svg viewBox="0 0 ${size} ${size}"><circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
    <circle class="${cls}" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}" stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${c * (1 - Math.max(0, Math.min(1, frac)))}"/></svg>`;
}
function countdown(days, windowDays, color) {
  const r = 26, c = 2 * Math.PI * r, frac = Math.max(0.04, Math.min(1, days / Math.max(1, windowDays)));
  return `<svg viewBox="0 0 64 64"><g transform="rotate(-90 32 32)"><circle class="cd-track" cx="32" cy="32" r="${r}" fill="none" stroke-width="6"/>
    <circle class="cd-fill" cx="32" cy="32" r="${r}" fill="none" stroke-width="6" stroke="${color}" stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${c * (1 - frac)}"/></g>
    <text x="32" y="31" text-anchor="middle" font-size="18" font-weight="800" fill="#12263A">${days}</text>
    <text x="32" y="45" text-anchor="middle" font-size="9.5" fill="#586979">${days === 1 ? "day" : "days"}</text></svg>`;
}
function spark(values, w = 64, h = 64, pad = 6) {
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [pad + (i * (w - 2 * pad)) / Math.max(1, values.length - 1), pad + (h - 2 * pad) * (1 - (v - lo) / span)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  let len = 0; for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  const last = pts[pts.length - 1], down = values[values.length - 1] < values[0];
  return `<svg viewBox="0 0 ${w} ${h}"><path class="spark draw" style="--len:${len.toFixed(0)};${down ? "" : "stroke:#B26600"}" d="${d}"/>
    <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${down ? "#1E8A4C" : "#B26600"}"/></svg>`;
}
function animateIn(root) {
  later(() => {
    root.querySelectorAll("[data-target]").forEach((c) => c.style.strokeDashoffset = c.dataset.target);
    root.querySelectorAll("[data-w]").forEach((b) => b.style.width = b.dataset.w);
    root.querySelectorAll("[data-left]").forEach((b) => b.style.left = b.dataset.left);
  });
}


/* ------------------------------------------------------------------ onboarding */
const OB = { step: 0, data: {} };
const GOALS = [
  ["deadlines", "Never miss a return window or bill", "#C0392B", "2 days left to return your headphones"],
  ["deals", "Tell me when cart prices drop", "#1A7F4B", "Earbuds in your cart dropped 21%"],
  ["overspend", "Stop me overspending", "#A65F00", "Eating out is $40 over this week"],
  ["save", "Help me save", "#0070E0", "Move $400 to savings on payday"],
];
let clockTimer = null;
function onboarding() {
  setChrome(false);
  const p = S.profile;
  OB.data = { uses: p.uses || "personal", monthly_budget: p.monthly_budget || 1500, monthly_income: p.monthly_income || 3000,
    pay_day: p.pay_day || 1, goals: p.goals.length ? p.goals : ["deadlines", "deals"], location_ok: false };
  OB.step = 0; drawOB();
}
function drawOB() {
  clearInterval(clockTimer);
  const d = OB.data;
  let preview = "", body = "", next = "Continue";
  if (OB.step === 0) {
    preview = `<div class="pv-clock"><div class="pv-face"><i></i></div><div class="pv-pill" id="pvpill"></div><p style="color:rgba(255,255,255,.75);max-width:260px;text-align:center;font-size:14px">The account switches by itself through the day.</p></div>`;
    body = `<h1>Hi ${esc(S.profile.name.split(" ")[0])}, what will you use ContextIQ for?</h1>
      <p class="muted">Pick both and it keeps them apart for you — business during work hours, personal after. One click switches it anytime, even right before you pay.</p>
      <div class="choice" role="group">${[["personal", "Personal", "Shopping, bills, budget"], ["business", "Business", "Suppliers, invoices, customers"], ["both", "Both", "Kept apart automatically"]]
        .map(([k, t, s]) => `<button data-uses="${k}" aria-pressed="${d.uses === k}"><b>${t}</b><small>${s}</small></button>`).join("")}</div>`;
  } else if (OB.step === 1) {
    preview = `<div class="ring pv-ring" style="width:170px;height:170px">${ringSvg(0.38, "fill", 170, 14)}<div class="ring-label"><b id="pvleft" style="font-size:26px">${money(d.monthly_budget * 0.62, undefined, 0)}</b><span>left this month</span></div></div>`;
    body = `<h1>Your month</h1><p class="muted">This drives the budget ring on your home page. Rough numbers are fine.</p>
      <label class="field">Monthly spending budget<input id="obbudget" type="number" inputmode="decimal" min="0" value="${esc(d.monthly_budget)}"></label>
      <label class="field">Take-home pay per month<input id="obincome" type="number" inputmode="decimal" min="0" value="${esc(d.monthly_income)}"></label>
      <label class="field">Payday (day of the month)<input id="obpay" type="number" min="1" max="28" value="${esc(d.pay_day)}"></label>`;
  } else if (OB.step === 2) {
    preview = `<div class="pv-cards" id="pvcards"></div>`;
    body = `<h1>What should we tell you about?</h1><p class="muted">These come first on your home page and in your notifications.</p>
      <div class="choice">${GOALS.map(([k, t]) => `<button data-goal="${k}" aria-pressed="${d.goals.includes(k)}"><b>${t}</b></button>`).join("")}</div>`;
  } else {
    preview = `<div class="pv-pin">${I.pin}</div>`;
    body = `<h1>Use your location? <span class="muted" style="font-weight:600;font-size:18px">Optional</span></h1>
      <p>It turns on travel mode when you're away from home and helps spot payments from places you've never been.</p>
      <p class="hint">Only your home point is saved, to your ContextIQ account. Without it, ContextIQ goes by the time of day.</p>`;
    next = "Use my location";
  }
  app.innerHTML = `<div class="ob-wrap"><div class="ob enter">
    <div class="ob-top"><span class="brand"><span class="mark"></span>ContextIQ</span><div class="ob-dots">${[0, 1, 2, 3].map((i) => `<i class="${i <= OB.step ? "on" : ""}"></i>`).join("")}</div></div>
    <div class="preview">${preview}</div>
    <div class="ob-form">${body}<div class="ob-actions"><button class="btn primary" id="obnext">${next}</button>
      ${OB.step === 3 ? `<button class="btn outline" id="obskip">Not now</button>` : ""}${OB.step ? `<button class="btn ghost" id="obback">Back</button>` : ""}</div></div></div></div>`;
  animateIn(app);
  if (OB.step === 0) {
    const states = d.uses === "both" ? ["Business · 10:00 · work hours", "Personal · 19:30 · after work", "Personal · Saturday"] : [`${cap(d.uses)} · always`];
    let i = 0; const pill = $("#pvpill");
    const tick = () => { pill.innerHTML = `<span>${esc(states[i++ % states.length])}</span>`; };
    tick(); clockTimer = setInterval(tick, 2000);
    app.querySelectorAll("[data-uses]").forEach((b) => b.onclick = () => { d.uses = b.dataset.uses; drawOB(); });
  }
  if (OB.step === 1) $("#obbudget").oninput = () => { $("#pvleft").textContent = money((Number($("#obbudget").value) || 0) * 0.62, undefined, 0); };
  if (OB.step === 2) {
    const draw = () => { $("#pvcards").innerHTML = GOALS.filter(([k]) => d.goals.includes(k)).map(([, , c, s], j) =>
      `<div class="pv-card" style="animation-delay:${j * 0.12}s"><i style="background:${c}"></i>${esc(s)}</div>`).join("") || `<div class="pv-card">Pick one to see an example</div>`; };
    draw();
    app.querySelectorAll("[data-goal]").forEach((b) => b.onclick = () => {
      const k = b.dataset.goal; d.goals = d.goals.includes(k) ? d.goals.filter((x) => x !== k) : [...d.goals, k];
      b.setAttribute("aria-pressed", d.goals.includes(k)); draw();
    });
  }
  $("#obback") && ($("#obback").onclick = () => { OB.step--; drawOB(); });
  $("#obskip") && ($("#obskip").onclick = () => finishOB(false));
  $("#obnext").onclick = () => {
    if (OB.step === 1) { d.monthly_budget = Number($("#obbudget").value) || null; d.monthly_income = Number($("#obincome").value) || null; d.pay_day = Number($("#obpay").value) || 1; }
    if (OB.step < 3) { OB.step++; drawOB(); return; }
    if (!navigator.geolocation) { finishOB(false); return; }
    $("#obnext").disabled = true; $("#obnext").textContent = "Waiting for your browser…";
    navigator.geolocation.getCurrentPosition((pos) => { d.home_lat = pos.coords.latitude; d.home_lon = pos.coords.longitude; finishOB(true); },
      () => { toast("ContextIQ will go by the time of day instead.", "No problem"); finishOB(false); }, { timeout: 10000, maximumAge: 600000 });
  };
}
async function finishOB(loc) {
  clearInterval(clockTimer);
  const d = OB.data; d.location_ok = loc;
  app.innerHTML = `<div class="building"><div class="ring" style="width:110px;height:110px">${ringSvg(1, "fill", 110, 10)}</div>
    <h2>Setting up your home page</h2><p class="muted" id="bmsg">Reading your purchases and bills…</p></div>`;
  app.querySelector(".fill").removeAttribute("data-target");
  await api("/api/profile/setup", { body: d });
  await wait(700); $("#bmsg").textContent = "Checking prices in your carts…";
  await wait(700);
  S.profile = await api("/api/profile");
  go("home");
}

/* ------------------------------------------------------------------ home */
const KIND = { deadline: "bell", price_drop: "tag", budget: "chart", bills: "calendar", renewal: "repeat", save: "piggy", today: "sun", travel: "plane", supplier: "doc" };
const TAG = { urgent: "Act soon", money: "Money", tip: "Good to know", good: "Nice" };
const CLR = { urgent: "#C0392B", money: "#E39B1B", tip: "#0070E0", good: "#1A7F4B" };
function cardViz(c) {
  const n = c.numbers || {};
  if ((c.kind === "deadline" || c.kind === "supplier") && n.days_left != null) return countdown(n.days_left, n.window_days || 14, CLR[c.priority]);
  if (c.kind === "price_drop" && n.history) return spark(n.history);
  return `<div class="tile">${I[KIND[c.kind]] || I.bell}</div>`;
}
function cardExtra(c) {
  const n = c.numbers || {};
  if (c.kind === "budget" && n.projected && n.budget) return paceBar(n.spent, n.projected, n.budget);
  return "";
}
function paceBar(spent, projected, budget) {
  const max = Math.max(projected, budget) * 1.05;
  return `<div class="pacebar" aria-hidden="true"><i data-w="${(spent / max * 100).toFixed(1)}%"></i><b data-left="${(projected / max * 100).toFixed(1)}%"></b><em style="left:${(budget / max * 100).toFixed(1)}%"></em></div>
    <div class="pacekey"><span style="--c:var(--acc)">Spent ${money(spent, undefined, 0)}</span><span style="--c:#E39B1B">Month-end at this pace ${money(projected, undefined, 0)}</span><span style="--c:var(--ink)">Budget ${money(budget, undefined, 0)}</span></div>`;
}
const ASK_ABOUT = { price_drop: (c) => `Can I afford the ${c.title.split(": ").slice(1).join(": ").replace(/\s−\d+%$/, "").toLowerCase()}?`,
  deadline: (c) => `Should I return the ${c.body.split(" from ")[0]}?`, budget: () => "How's my budget looking?", bills: () => "What bills are coming up?",
  supplier: () => "Is the supplier invoice correct?" };
function cardHtml(c, j, wide = false) {
  const q = ASK_ABOUT[c.kind]?.(c);
  return `<article class="card ${esc(c.priority)} ${wide ? "wide" : ""} enter" style="animation-delay:${0.12 + j * 0.07}s">
    <div class="viz">${cardViz(c)}</div>
    <div><span class="tag ${esc(c.priority)}">${TAG[c.priority]}</span><h3>${esc(c.title)}</h3><p>${esc(c.body)}</p>${cardExtra(c)}
    <div class="act">${c.action ? `<button class="btn primary small" data-go="${esc(c.action.go)}" data-case="${esc(c.action.case_id || "")}" data-item="${esc(c.action.cart_item || "")}">${esc(c.action.label)}</button>` : ""}
      ${q ? `<button class="btn ghost small" data-ask="${esc(q)}">Ask about this</button>` : ""}</div></div></article>`;
}
function insightsUrl() {
  const now = new Date(), q = new URLSearchParams({ hour: now.getHours(), weekday: (now.getDay() + 6) % 7 });
  if (S.account) q.set("account", S.account);
  if (S.pos) { q.set("lat", S.pos.lat); q.set("lon", S.pos.lon); }
  return "/api/insights?" + q;
}
async function loadInsights() {
  const h = await api(insightsUrl()); S.home = h; S.cards = h.cards;
  document.body.classList.toggle("business", h.context.account === "business");
  drawAccount(); notify(h.cards);
  return h;
}
function recHtml(r, j = 0) {
  return `<article class="card rec enter" style="animation-delay:${0.15 + j * 0.08}s" data-rec="${esc(r.id)}">
    <div class="viz"><div class="tile">${I[{ plan: "spark", subscription: "repeat", cap: "chart", save: "piggy", invest: "invest", wait: "tag" }[r.kind]] || I.spark}</div></div>
    <div><span class="tag plan">${r.kind === "plan" ? "Your plan" : "Recommended"}</span><h3>${esc(r.title)}</h3><p>${esc(r.body)}</p>
      ${r.steps?.length ? `<ol class="plan">${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}
      <div class="act"><button class="btn primary small" data-rec-yes="${esc(r.id)}" data-rec-go="${esc(r.go || "")}">Do it</button><button class="btn ghost small" data-rec-no="${esc(r.id)}">Not for me</button></div></div></article>`;
}
function bindRecs(root) {
  root.querySelectorAll("[data-rec-yes]").forEach((b) => b.onclick = () => {
    api("/api/feedback", { body: { context: "recs", arm: b.dataset.recYes, reward: 1 } }).catch(() => {});
    toast("ContextIQ will remind you at the right moment.", "Added to your plan", "good");
    if (b.dataset.recGo && b.dataset.recGo !== S.tab) go(b.dataset.recGo);
  });
  root.querySelectorAll("[data-rec-no]").forEach((b) => b.onclick = () => {
    api("/api/feedback", { body: { context: "recs", arm: b.dataset.recNo, reward: 0 } }).catch(() => {});
    const card = b.closest("[data-rec]"); card.style.transition = "opacity .3s, transform .3s"; card.style.opacity = 0; card.style.transform = "scale(.97)";
    setTimeout(() => card.remove(), 300); toast("Got it — you'll see fewer like this.", "Noted");
  });
}
const BILL_ICON = { bill: "bolt", subscription: "repeat", supplier_payment: "doc", emi: "calendar" };
function billRow(b) {
  return `<div class="bill"><div class="viz">${countdown(Math.max(0, b.days_left), 14, b.days_left <= 1 ? "#C0392B" : b.days_left <= 3 ? "#E39B1B" : "#1A7F4B")}</div>
    <div><b>${esc(b.title)}</b><small>${b.days_left <= 0 ? "Due today" : b.days_left === 1 ? "Due tomorrow" : `Due ${fmtDate(b.due)}`}${b.autopay ? " · renews automatically" : ""}${b.purpose === "business" ? " · business" : ""}</small></div>
    <div class="bill-r"><span class="num">${money(b.amount)}</span>${b.autopay ? "" : `<button class="btn pay small" data-bill="${esc(b.id)}">Pay</button>`}</div></div>`;
}
const views = {};
views.home = async () => {
  const [h, cases, bills, recs] = await Promise.all([loadInsights(), api("/api/cases"), api("/api/bills"), api("/api/recommendations")]);
  S.home = h;
  S.bills = bills;
  const ctx = h.context, biz = ctx.account === "business";
  const month0 = new Date(); month0.setDate(1); month0.setHours(0, 0, 0, 0);
  const bought = cases.filter((c) => new Date(c.created_at) >= month0 && c.payment_state === "captured" && (c.purpose === "business") === biz);
  const myBills = bills.filter((b) => (b.purpose === "business") === biz);
  const now = h.cards.filter((c) => !["bills", "renewal", "supplier"].includes(c.kind)).slice(0, 2);
  const rec = biz ? null : recs.items[0];
  const sm = h.summary;
  const urgent = h.cards.find((c) => c.priority === "urgent"), nextBill = myBills.find((b) => !b.autopay);
  const line = [urgent ? `<b>${esc(urgent.title)}</b>` : "", nextBill ? `${esc(nextBill.title)} due ${nextBill.days_left <= 1 ? "tomorrow" : `in ${nextBill.days_left} days`}` : ""].filter(Boolean).join(" · ")
    || "Nothing urgent. ContextIQ is watching your deadlines, carts and budget.";
  const realBal = sm.balance != null ? Number(sm.balance) : 1450.0;
  const billsTot = sm.bills_total != null ? Number(sm.bills_total) : myBills.reduce((s, b) => s + b.amount, 0);
  const freeCash = sm.free_cash != null ? Number(sm.free_cash) : Math.round((realBal - billsTot) * 100) / 100;
  const monthlyInc = sm.monthly_income != null ? Number(sm.monthly_income) : (S.profile?.monthly_income || 4000);
  const nextPaydayStr = sm.next_payday || "Nov 18";

  app.innerHTML = `<section class="hero-band enter">
      <div class="hero-top"><div><span class="ctx-chip"><i></i>${esc(cap(ctx.account))} · ${esc(ctx.reason)}${ctx.travel ? " · travel mode" : ""}</span>
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
          <h1 style="margin-bottom:2px">${esc(h.greeting)}</h1>
          <span style="font-size:12px;background:rgba(255,255,255,0.18);color:#FFF;padding:2px 10px;border-radius:12px;font-weight:600">● PayPal: ${esc(S.profile?.paypal_email || "sb-hfln853812063@personal.example.com")}</span>
        </div>
        <p class="hero-line">${line}</p></div>
        <div class="hero-stat"><small>${biz ? "Business available balance" : "Available account balance"} <button class="bb-edit" id="editBalBtn">Edit</button></small><b class="num" id="heroBal">${money(0, undefined, 2)}</b>
          <small style="margin-top:5px;color:rgba(255,255,255,.9)">Safe to spend: <strong style="color:var(--gold);font-size:15px">${money(freeCash, undefined, 2)}</strong></small>
        </div></div>

      <div class="balance-breakdown">
        <div class="bb-item">
          <small>Actual Account Funds</small>
          <b>${money(realBal)}</b>
        </div>
        <div class="bb-item">
          <small>Committed to Upcoming Bills</small>
          <b style="color:#FFA69E">-${money(billsTot)}</b>
        </div>
        <div class="bb-item highlight">
          <small>Safe to Spend Right Now</small>
          <b>${money(freeCash)}</b>
        </div>
        <div class="bb-item">
          <small>Next Salary Inflow</small>
          <b>+${money(monthlyInc)} <span style="font-size:11px;font-weight:600;opacity:.85">(${fmtDate(nextPaydayStr)})</span></b>
        </div>
      </div>

      <div class="flow-bar">
        ${I.spark}
        <span><b>Money Flow Consideration:</b> ContextIQ tracks your balance against actual funds in hand (<b>${money(realBal)}</b>), reserving <b>${money(billsTot)}</b> for upcoming bills so you don't rely prematurely on your <b>${money(monthlyInc)}</b> salary before ${fmtDate(nextPaydayStr)}.</span>
      </div>

      <div class="actions">
        <button data-act="scan"><span>${I.qr}</span>Scan to pay</button>
        <button data-act="check-bills"><span>${I.bolt}</span>Check & pay bills</button>
        <button data-tab-go="notices"><span>${I.spark}</span>1-Way Notices</button>
        <button data-tab-go="cart"><span>${I.cart}</span>Your cart</button>
        <button data-tab-go="budget"><span>${I.chart}</span>Budget & Flow</button>
      </div>
    </section>
    <div class="grid2">
      <div>
        <div class="panel-title"><h2>${ctx.part === "morning" ? "For today" : "Right now"}</h2></div>
        <div class="stack">${now.map((c, j) => cardHtml(c, j)).join("") || `<div class="panel">Nothing needs you right now.</div>`}
          ${rec ? recHtml(rec, 2) : ""}</div>
        ${biz ? "" : `<button class="panel invest-teaser enter" data-tab-go="invest" style="animation-delay:.35s">
          <span class="tile">${I.invest}</span><span><b>${recs.investable ? `You could safely put away ${money(recs.investable, undefined, 0)}` : "Grow what you don't need this month"}</b>
          <small>Savings, short-term and index options explained simply</small></span><span class="chev">›</span></button>`}
      </div>
      <div>
        <section class="panel enter" id="billsPanel" style="animation-delay:.1s"><div class="panel-title"><h2>${biz ? "Payments due" : "Bills and payments"}</h2><button class="link" id="checkAllBills">Check all bills ›</button></div>
          <div class="bills">${myBills.map(billRow).join("") || `<p class="hint">Nothing due. Nice.</p>`}</div></section>
        <section class="panel enter" style="animation-delay:.2s"><div class="panel-title"><h2>Bought this month</h2><button class="link" data-tab-go="history">History</button></div>
          ${bought.length ? `<div class="bought">${bought.map((c, j) => `<button class="bought-i" data-case="${esc(c.id)}" style="animation-delay:${0.25 + j * 0.06}s"><span class="tile">${c.channel === "invoice" ? I.doc : c.channel === "bill" ? I.bolt : I.box}</span>
            <b>${esc(c.title)}</b><small class="num">${money(c.amount, c.currency)}</small></button>`).join("")}</div>
            <p class="hint" style="margin-top:10px">${bought.length} purchase${bought.length > 1 ? "s" : ""} · ${money(bought.reduce((s, c) => s + c.amount, 0))} this month</p>` : `<p class="hint">Nothing yet this month.</p>`}</section>
      </div>
    </div>`;
  animateIn(app); bindPage(); bindRecs(app);
  countUp($("#heroBal"), realBal, (v) => money(v, undefined, 2));
  $("#editBalBtn") && ($("#editBalBtn").onclick = () => editBalance(realBal));
  $("#checkAllBills") && ($("#checkAllBills").onclick = openBillsManager);
  app.querySelector("[data-act=scan]").onclick = openScanner;
  app.querySelector("[data-act=check-bills]").onclick = openBillsManager;
  app.querySelectorAll("[data-bill]").forEach((b) => b.onclick = () => payBill(b.dataset.bill));
};

function editBalance(currentBal) {
  openSheet(`
    <button class="btn-back small" onclick="sheet.close()">${I.back} Back</button>
    <h2>Update Account Balance</h2>
    <p class="muted">Enter the actual amount of money currently in your PayPal or connected bank account. ContextIQ tracks spending against real funds in hand minus upcoming bills, keeping your monthly salary as inflow context.</p>
    <label class="field">Actual Account Balance ($)<input type="number" id="newBal" step="0.01" min="0" value="${currentBal || 0}"></label>
    <button class="btn primary wide" id="saveBal">Save Balance</button>
    <button class="btn ghost wide" onclick="sheet.close()">Cancel</button>
  `);
  $("#saveBal").onclick = async () => {
    const val = parseFloat($("#newBal").value) || 0;
    await api("/api/balance", { body: { balance: val } });
    sheet.close();
    toast(`Available balance updated to ${money(val)}`, "Balance Saved", "good");
    await views.home();
  };
}

function openBillsManager() {
  const pBills = (S.bills || []).filter((b) => b.purpose !== "business");
  const bBills = (S.bills || []).filter((b) => b.purpose === "business");
  const autoBills = (S.bills || []).filter((b) => b.autopay);
  const totalDue = (S.bills || []).reduce((s, b) => s + b.amount, 0);
  const realBal = S.home?.summary?.balance ?? 1450.0;
  const afterBills = Math.round((realBal - totalDue) * 100) / 100;

  openSheet(`
    <button class="btn-back small" onclick="sheet.close()">${I.back} Back</button>
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:6px">
      <h2>Check Bills & Subscriptions</h2>
      <span class="num" style="font-weight:800;color:var(--coral);font-size:18px">${money(totalDue)} due</span>
    </div>
    <p class="muted">Inspect all upcoming obligations, due dates, and their exact impact on your current account balance.</p>

    <div class="note ${afterBills >= 0 ? "ok" : "warn"}" style="margin:14px 0">
      <b>Cash Balance Impact:</b> Paying all bills (${money(totalDue)}) leaves <b>${money(afterBills)}</b> in your account before your next salary arrives.
    </div>

    <div class="bills-filter" role="tablist">
      <button class="bf-btn" data-f="all" aria-pressed="true">All (${(S.bills || []).length})</button>
      <button class="bf-btn" data-f="personal" aria-pressed="false">Personal (${pBills.length})</button>
      <button class="bf-btn" data-f="business" aria-pressed="false">Business (${bBills.length})</button>
      <button class="bf-btn" data-f="auto" aria-pressed="false">Autopay (${autoBills.length})</button>
    </div>

    <div class="bills" id="billsListModal" style="max-height:55vh;overflow-y:auto;padding-right:4px">
      ${(S.bills || []).map(billRow).join("") || `<p class="hint">No bills due.</p>`}
    </div>
  `);

  const listEl = $("#billsListModal");
  document.querySelectorAll(".bf-btn").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".bf-btn").forEach((x) => x.setAttribute("aria-pressed", x === b));
      const f = b.dataset.f;
      const filtered = (S.bills || []).filter((item) => {
        if (f === "personal") return item.purpose !== "business";
        if (f === "business") return item.purpose === "business";
        if (f === "auto") return item.autopay;
        return true;
      });
      listEl.innerHTML = filtered.map(billRow).join("") || `<p class="hint">No bills in this category.</p>`;
      listEl.querySelectorAll("[data-bill]").forEach((btn) => btn.onclick = () => payBill(btn.dataset.bill));
    };
  });
  listEl.querySelectorAll("[data-bill]").forEach((btn) => btn.onclick = () => payBill(btn.dataset.bill));
}
function bindPage() {
  app.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => {
    if (b.dataset.case) { openCase(b.dataset.case); return; }
    if (b.dataset.item) { go("cart").then(() => buyWatched(b.dataset.item)); return; }
    go({ pay: "cart", activity: "history", home: "home" }[b.dataset.go] || b.dataset.go);
  });
  app.querySelectorAll("[data-ask]").forEach((b) => b.onclick = () => openAssistant(b.dataset.ask));
  app.querySelectorAll("[data-tab-go]").forEach((b) => b.onclick = () => go(b.dataset.tabGo));
  app.querySelectorAll("[data-case]").forEach((b) => { if (!b.dataset.go) b.onclick = () => openCase(b.dataset.case); });
}

/* ------------------------------------------------------------------ bills + scanner */
function payBill(id) {
  const b = (S.bills || []).find((x) => x.id === id); if (!b) return;
  S.cart = { merchant: b.title.split(" — ")[0], items: [{ name: b.title, unit_price: b.amount, quantity: 1 }], purpose: b.purpose };
  openSheet(`<h2>${esc(b.title)}</h2><p class="muted">${b.days_left <= 0 ? "Due today" : `Due ${fmtDate(b.due)}`} · <b class="num" style="color:var(--ink)">${money(b.amount)}</b></p>
    <div class="note ${b.days_left <= 1 ? "warn" : "ok"}">${b.days_left <= 1 ? "Paying now avoids a late fee." : `Paying ${b.days_left} days early is fine — your balance covers your other bills too.`}</div>
    <div id="payarea"></div>${S.config.paypal_env === "mock" ? `<p class="hint" style="text-align:center;margin-top:8px">Test mode — no real money moves.</p>` : ""}`);
  payButton($("#payarea"), () => api(`/api/bills/${id}/checkout`, { method: "POST" }));
}
let scanStream = null;
function stopScan() { scanStream?.getTracks().forEach((t) => t.stop()); scanStream = null; }

async function openScanner() {
  sheet.onclose = stopScan;
  openSheet(`<h2>Scan to pay</h2><p class="muted">Point your camera at the shop's ContextIQ QR. ContextIQ checks the shop's signature before you pay.</p>
    <div class="scanbox"><video id="cam" playsinline muted></video><div class="scanline"></div></div>
    <p class="hint" id="scanmsg">Starting camera…</p>
    <button class="btn outline wide" id="demoqr">Try a demo shop QR</button>`);
  $("#demoqr").onclick = async () => {
    const q = await fetch("/api/qr/create", { method: "POST", headers: { "Content-Type": "application/json", "X-User-Id": "brightmart" },
      body: JSON.stringify({ items: [{ name: "USB-C charger", unit_price: 24.99, quantity: 1 }, { name: "Screen protector", unit_price: 9.5, quantity: 2 }], policy_text: DEMO_POLICY }) }).then((r) => r.json());
    handleScan(q.qr_token);
  };
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) { $("#scanmsg").textContent = "This browser can't scan with the camera. Use the demo shop QR instead."; $(".scanbox").remove(); return; }
  try {
    scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    const v = $("#cam"); v.srcObject = scanStream; await v.play();
    $("#scanmsg").textContent = "Looking for a QR code…";
    const det = new BarcodeDetector({ formats: ["qr_code"] });
    const loop = async () => {
      if (!scanStream) return;
      const codes = await det.detect(v).catch(() => []);
      if (codes[0]) { stopScan(); handleScan(codes[0].rawValue); return; }
      requestAnimationFrame(loop);
    };
    loop();
  } catch { $("#scanmsg").textContent = "No camera access. Use the demo shop QR instead."; $(".scanbox")?.remove(); }
}
async function handleScan(raw) {
  stopScan();
  const r = await api("/api/qr/scan", { body: { token: raw } });
  if (!r.ok) { openSheet(`<h2>Don't pay this code</h2><div class="note bad">${esc(r.error)}</div><p class="muted">The shop's signature didn't check out, so ContextIQ blocked it.</p>`); return; }
  const total = r.items.reduce((s, i) => s + i.unit_price * (i.quantity || 1), 0);
  S.cart = { merchant: r.verified_merchant, items: r.items, purpose: "personal" };
  openSheet(`<h2>${esc(r.verified_merchant)}</h2><p class="muted"><span class="pill good">Verified shop</span> · <b class="num" style="color:var(--ink)">${money(total)}</b></p>
    <div class="note">${r.items.map((i) => `${esc(i.name)} × ${i.quantity || 1} · ${money(i.unit_price * (i.quantity || 1))}`).join("<br>")}</div>
    <div id="payarea"></div>`);
  payButton($("#payarea"), async () => r);
}

/* ------------------------------------------------------------------ account (context label) */
function drawAccount() {
  const ctx = S.home?.context; if (!ctx) return;
  $("#acct").innerHTML = `<span class="acct-why" style="padding:6px 12px">${esc(cap(ctx.account))} · ${esc(ctx.reason)}</span>`;
}

/* ------------------------------------------------------------------ notifications */
const seen = new Set(JSON.parse(localStorage.getItem("ciq-seen") || "[]"));
const toasted = new Set(JSON.parse(sessionStorage.getItem("ciq-toasted") || "[]"));
const extraNotes = JSON.parse(localStorage.getItem("ciq-notes") || "[]");
function noteKey(c) { return `${c.id}|${c.title}`; }
function allNotes() { return [...extraNotes.slice(-10).reverse(), ...S.cards]; }
function notify(cards) {
  drawBadge();
  const fresh = cards.filter((c) => (c.priority === "urgent" || c.priority === "money") && !toasted.has(noteKey(c))).slice(0, 2);
  fresh.forEach((c, j) => setTimeout(() => {
    toast(c.body, c.title, c.priority, () => cardAction(c), 7000);
    if (localStorage.getItem("ciq-push") === "on" && "Notification" in window && Notification.permission === "granted" && document.hidden)
      new Notification(c.title, { body: c.body, tag: c.id });
  }, 600 + j * 700));
  fresh.forEach((c) => toasted.add(noteKey(c)));
  sessionStorage.setItem("ciq-toasted", JSON.stringify([...toasted]));
}
function pushNote(title, body, priority = "good") {
  extraNotes.push({ id: "n" + Date.now(), title, body, priority, kind: "event", at: Date.now() });
  localStorage.setItem("ciq-notes", JSON.stringify(extraNotes.slice(-20)));
  toast(body, title, priority); drawBadge();
  if (localStorage.getItem("ciq-push") === "on" && "Notification" in window && Notification.permission === "granted") new Notification(title, { body });
}
function drawBadge() {
  const n = allNotes().filter((c) => !seen.has(noteKey(c))).length;
  $("#badge").hidden = !n; $("#badge").textContent = n > 9 ? "9+" : n;
}
function cardAction(c) {
  if (c.action?.case_id) openCase(c.action.case_id);
  else if (c.action?.cart_item) go("cart").then(() => buyWatched(c.action.cart_item));
  else if (c.action?.go) go(c.action.go);
}
$("#bell").onclick = (e) => {
  e.stopPropagation();
  const dd = $("#notes"), open = dd.hidden;
  if (!open) { dd.hidden = true; $("#bell").setAttribute("aria-expanded", "false"); return; }
  const list = allNotes();
  const pushOn = localStorage.getItem("ciq-push") === "on" && "Notification" in window && Notification.permission === "granted";
  dd.innerHTML = `<div class="dd-head"><b>Notifications</b><span class="hint">${list.length}</span></div>
    ${list.map((c, j) => `<div class="dd-item ${seen.has(noteKey(c)) ? "" : "unread"}" data-n="${j}"><i style="background:${CLR[c.priority] || CLR.tip}"></i><div><b>${esc(c.title)}</b><span>${esc(c.body)}</span></div></div>`).join("") || `<p class="hint" style="padding:0 16px">You're all caught up.</p>`}
    <div class="dd-foot"><span>${pushOn ? "Alerts on this device are on." : "Get alerts even when this tab is in the background."}</span>
      ${"Notification" in window ? `<button class="btn ${pushOn ? "ghost" : "outline"} small" id="pushbtn">${pushOn ? "Turn off" : "Turn on"}</button>` : ""}</div>`;
  dd.hidden = false; $("#bell").setAttribute("aria-expanded", "true");
  dd.querySelectorAll("[data-n]").forEach((it) => it.onclick = () => { dd.hidden = true; cardAction(list[Number(it.dataset.n)]); });
  $("#pushbtn") && ($("#pushbtn").onclick = async (ev) => {
    ev.stopPropagation();
    if (pushOn) { localStorage.setItem("ciq-push", "off"); dd.hidden = true; toast("Device alerts are off.", "Done"); return; }
    const p = await Notification.requestPermission();
    if (p === "granted") { localStorage.setItem("ciq-push", "on"); new Notification("ContextIQ alerts are on", { body: "You'll hear about deadlines, price drops and payments." }); }
    else toast("Your browser blocked notifications. You'll still see them here.", "Not turned on");
    dd.hidden = true;
  });
  list.forEach((c) => seen.add(noteKey(c))); localStorage.setItem("ciq-seen", JSON.stringify([...seen].slice(-200))); setTimeout(drawBadge, 400);
};
document.addEventListener("click", (e) => { if (!$("#notes").hidden && !e.target.closest(".bell-wrap")) $("#notes").hidden = true; });
setInterval(() => { if (S.profile?.setup_done) loadInsights().catch(() => {}); }, 60000);

/* ------------------------------------------------------------------ pay */
function buyWatched(id) {
  const it = (S.watch || []).find((x) => x.id === id);
  if (!it) { api("/api/cart/watch").then((w) => { S.watch = w; if (w.find((x) => x.id === id)) buyWatched(id); }); return; }
  const bm = it.merchant.startsWith("BrightMart");
  startPay({ merchant: it.merchant, items: [{ name: it.name, unit_price: it.now, quantity: 1 }], currency: it.currency, policy_text: bm ? DEMO_POLICY : "", seller_id: bm ? "brightmart" : null });
}
const DEMO_POLICY = `You may return most items within 30 days of delivery for a full refund to the original payment method.
Items must be unused, in original packaging, with proof of purchase.
Defective items qualify for a 7-day replacement from the date of delivery.
All headphones and speakers carry a 1-year limited warranty.
In-ear earbuds are non-returnable once opened for hygiene reasons.
Customer pays return shipping unless the item arrived defective.`;

function notReturnable(title, lines) {
  const line = (lines || []).find((l) => /^not returnable/i.test(l));
  if (!line) return "";
  const words = String(title).toLowerCase().match(/[a-z]{4,}/g) || [];
  return words.some((w) => line.toLowerCase().includes(w.replace(/s$/, ""))) ? line.replace(/^not returnable:\s*/i, "") + "." : "";
}
const _unusedFmt = (d) => { const x = new Date(d); return x.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(x.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}) }); };
const sheet = $("#sheet");
function openSheet(html) { $("#sheet-body").innerHTML = html; if (!sheet.open) sheet.showModal(); animateIn(sheet); }
sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

async function startPay(cart) {
  S.cart = cart;
  const total = cart.items.reduce((s, i) => s + i.unit_price * (i.quantity || 1), 0);
  openSheet(`<h2>${esc(cart.items.map((i) => i.name).join(", "))}</h2><p class="muted">${esc(cart.merchant)} · <span class="num">${money(total)}</span></p>
    <ul class="steps"><li class="now">Reading the store's terms</li><li>Checking your budget</li><li>Choosing the account</li></ul>`);
  const [a, acct] = await Promise.all([api("/api/cart/analyze", { body: cart }),
    api("/api/accounts/classify", { body: { payee: cart.merchant, description: cart.items.map((i) => i.name).join(", "), amount: total } })]);
  const lis = sheet.querySelectorAll(".steps li");
  for (let k = 0; k < lis.length; k++) { lis[k].className = "done"; if (lis[k + 1]) lis[k + 1].className = "now"; await wait(260); }
  const ctxAcct = S.home?.context?.account || "personal";
  cart.purpose = acct.source === "your earlier choice" ? acct.purpose : (S.profile.uses === "both" ? ctxAcct : S.profile.uses);
  cart.why = acct.source === "your earlier choice" ? acct.why
    : S.profile.uses === "both" ? `you're in ${ctxAcct} mode (${S.home?.context?.reason || "right now"})` : "your only account";
  cart.manual = false;
  drawPaySheet(a, acct, total);
}
function drawPaySheet(a, acct, total) {
  const cart = S.cart, p = a.policy, biz = cart.purpose === "business";
  const verdict = biz ? { cls: "", msg: "Business purchase — kept out of your personal budget and filed with your business records." }
    : { cls: a.budget.verdict === "ok" ? "ok" : a.budget.verdict === "tight" ? "warn" : "bad", msg: a.budget.message };
  const terms = p ? p.summary.slice(0, 4) : [];
  openSheet(`<h2>${esc(cart.items.map((i) => i.name).join(", "))}</h2><p class="muted">${esc(cart.merchant)} · <b class="num" style="color:var(--ink)">${money(total)}</b></p>
    <div style="font-weight:700;font-size:14px;margin-top:12px">Pay from</div>
    <div class="seg" role="group" aria-label="Account"><button data-acct="personal" aria-pressed="${!biz}">Personal</button><button data-acct="business" aria-pressed="${biz}">Business</button></div>
    <p class="hint" style="margin:4px 2px 0">${cart.manual ? "Switched. ContextIQ will use this for this store from now on." : `Picked automatically — ${esc(cart.why)}. Tap to switch before you pay.`}</p>
    ${notReturnable(cart.items.map((i) => i.name).join(" "), p?.summary) ? `<div class="note warn"><b>Heads up:</b> ${esc(notReturnable(cart.items.map((i) => i.name).join(" "), p.summary))}</div>` : ""}
    <div class="note ${verdict.cls}">${esc(verdict.msg)}</div>
    ${terms.length ? `<div class="note"><b>What you're agreeing to</b><ul style="margin:6px 0 0 18px;padding:0">${terms.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>` : ""}
    ${p?.injection_flags?.length ? `<div class="note warn">This store's page had hidden text trying to instruct AI assistants. ContextIQ ignored it.</div>` : ""}
    <div class="note ok" style="margin:12px 0 6px 0;display:flex;align-items:center;justify-content:space-between">
      <div>
        <span class="hint" style="font-size:11px;text-transform:uppercase;font-weight:700;color:#166534">Linked PayPal Payer</span><br>
        <b style="font-size:13.5px;color:var(--ink)">${esc(S.profile?.paypal_email || "sb-hfln853812063@personal.example.com")}</b>
      </div>
      <span class="pill good">Auto-Linked</span>
    </div>
    <div id="payarea"></div>
    ${S.config.paypal_env === "mock" ? `<p class="hint" style="text-align:center;margin-top:8px">Test mode — no real money moves.</p>` : ""}`);
  sheet.querySelectorAll("[data-acct]").forEach((b) => b.onclick = async () => {
    if (b.dataset.acct === cart.purpose) return;
    cart.purpose = b.dataset.acct; cart.manual = true;
    api("/api/accounts/remember", { body: { payee: cart.merchant, purpose: cart.purpose } }).catch(() => {});
    drawPaySheet(a, acct, total);
  });
  payButton($("#payarea"));
}
function payButton(el, create = () => api("/api/checkout", { body: S.cart })) {
  if (S.config.paypal_env !== "mock" && S.config.paypal_client_id) {
    el.innerHTML = `<div id="pp-buttons" style="margin-top:10px"></div>
      <div style="margin-top:10px;font-size:12px;color:var(--muted);text-align:center">
        PayPal Sandbox popup issue? <a href="#" id="direct-pp-link" style="color:var(--blue);text-decoration:underline">Open in fresh tab</a> · approved there? <a href="#" id="finish-pp-btn" style="color:var(--blue);text-decoration:underline">Finish payment</a>
      </div>`;
    loadPayPalSdk().then(() => window.paypal.Buttons({
      style: { layout: "vertical", shape: "pill", label: "pay" },
      createOrder: async () => { const r = await create(); S.checkout = r; sessionStorage.setItem("ciq-checkout", JSON.stringify(r)); return r.order.order_id; },
      onApprove: () => complete(),
      onError: (err) => toast("PayPal couldn't start the payment: " + (err?.message || err)),
    }).render("#pp-buttons")).catch(() => el.innerHTML = `<div class="note bad">Couldn't load PayPal's button. Check your internet connection.</div>`);

    setTimeout(() => {
      const dirLink = $("#direct-pp-link");
      if (dirLink) {
        dirLink.onclick = async (e) => {
          e.preventDefault();
          const r = await create();
          S.checkout = r;
          sessionStorage.setItem("ciq-checkout", JSON.stringify(r));
          if (r.order?.approve_url) {
            window.open(r.order.approve_url, "_blank");
          } else {
            toast("Order created: " + r.order?.order_id);
          }
        };
      }
      const finishBtn = $("#finish-pp-btn");
      if (finishBtn) {
        finishBtn.onclick = (e) => {
          e.preventDefault();
          if (!S.checkout) return toast("Open PayPal first, approve there, then come back here.");
          complete();  // capture is refused unless PayPal reports the order approved
        };
      }
    }, 100);
    return;
  }
  el.innerHTML = `<button class="btn pay wide" id="paynow">${I.lock}Pay with PayPal</button>`;
  $("#paynow").onclick = async () => {
    $("#paynow").disabled = true;
    el.innerHTML = `<ul class="steps"><li class="now">Saving exactly what you're agreeing to</li><li>Approving on PayPal</li><li>Completing payment</li></ul>`;
    const lis = el.querySelectorAll("li");
    S.checkout = await create();
    lis[0].className = "done"; lis[1].className = "now"; await wait(500);
    await api(`/api/cases/${S.checkout.case_id}/approve-mock`, { method: "POST" });
    lis[1].className = "done"; lis[2].className = "now"; await wait(300);
    complete();
  };
}
let sdkP = null;
function loadPayPalSdk() {
  if (window.paypal) return Promise.resolve();
  sdkP ||= new Promise((res, rej) => { const s = document.createElement("script");
    s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(S.config.paypal_client_id)}&currency=${encodeURIComponent(S.config.currency || "USD")}&intent=capture`;
    s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  return sdkP;
}
async function complete(code) {
  const co = S.checkout;
  const r = await api(`/api/cases/${co.case_id}/capture`, { body: { approval_token: co.approval_token, step_up_code: code || null } });
  if (r.gateway === "step_up") {
    const dlg = $("#stepup");
    $("#stepup-why").textContent = "This payment is " + r.reasons.join(" and ") + ", so we want to be sure it's you.";
    $("#stepup-code").textContent = r.step_up_code_demo; $("#stepup-input").value = "";
    if (sheet.open) sheet.close();
    dlg.showModal();
    $("#stepup-ok").onclick = () => { dlg.close(); openSheet(`<ul class="steps"><li class="done">Confirmed it's you</li><li class="now">Completing payment</li></ul>`); complete($("#stepup-input").value.trim()); };
    $("#stepup-cancel").onclick = () => dlg.close();
    return;
  }
  if (!r.ok) { openSheet(`<h2>Payment not completed</h2><div class="note bad">${esc(r.error || (r.reasons || []).join("; "))}</div><p class="muted">You haven't been charged.</p>`); return; }
  sessionStorage.removeItem("ciq-checkout");
  store.set("ciq-tour-case", co.case_id); refreshTour();
  if (S.config.paypal_env === "mock") api("/api/mock/deliver-webhooks", { method: "POST" }).catch(() => {});
  pushNote("Payment complete", `${money(S.checkout?.amount ?? S.cart?.items?.reduce((s, i) => s + i.unit_price * (i.quantity || 1), 0))} to ${S.cart?.merchant || "the store"} from your ${S.cart?.purpose || ""} account. Return deadlines are now on your home page.`);
  openSheet(`<svg class="paid-check" viewBox="0 0 84 84"><circle cx="42" cy="42" r="40"/><path d="M26 43l11 11 21-23"/></svg>
    <h2 style="text-align:center">Paid</h2><p class="muted" style="text-align:center">${esc(S.cart?.merchant || "")} · ${cap(S.cart?.purpose || "")} account</p>
    <div class="note">ContextIQ saved the store's terms with this purchase. You'll see return and warranty deadlines on your home screen — no need to keep the receipt.</div>
    <button class="btn primary wide" id="seeit">See it in History</button>`);
  $("#seeit").onclick = () => { sheet.close(); go("history").then(() => openCase(co.case_id)); };
}



/* ------------------------------------------------------------------ cart intelligence */
views.cart = async () => {
  const [h, items, recs] = await Promise.all([loadInsights(), api("/api/cart/watch"), api("/api/recommendations")]);
  S.watch = items;
  const drops = Object.fromEntries(h.cards.filter((c) => c.kind === "price_drop").map((c) => [c.action?.cart_item, c]));
  const verdict = (it) => {
    const d = drops[it.id];
    if (d) return d.numbers.fits_budget ? ["good", "Good time to buy", d.body.split(". ").slice(1).join(". ")] : ["warn", "Wait until payday", d.body.split(". ").slice(1).join(". ")];
    if (it.now > it.prices[0]) return ["warn", "Wait", `Up ${money(it.now - it.prices[0])} since you added it. It's been cheaper — ContextIQ will tell you when it drops.`];
    return ["", "Watching", "No change yet. You'll get a notification if it drops."];
  };
  app.innerHTML = `${backBtnHtml("home")}
    <div class="page-head enter"><div><h1>Cart</h1><p class="muted">ContextIQ watches the price of everything in your carts and checks each one against your actual cash balance and upcoming bills.</p></div>
      <a class="btn outline" href="/demo-store/">Shop the demo store</a></div>
    <div class="watchgrid">${items.map((it, j) => { const was = Math.max(...it.prices.slice(0, -1), it.prices[0]); const drop = it.now < was; const [cls, head, why] = verdict(it);
      return `<section class="panel enter" style="animation-delay:${j * 0.08}s"><div class="watch"><div><small class="hint">${esc(it.merchant)}</small><h3>${esc(it.name)}</h3>
        <div><span class="price-now num">${money(it.now)}</span>${drop ? `<span class="price-was num">${money(was)}</span>` : ""}</div>
        <div style="margin-top:6px">${drop ? `<span class="pill good">Down ${Math.round((1 - it.now / was) * 100)}%</span>` : it.now > it.prices[0] ? `<span class="pill warn">Up since you added it</span>` : `<span class="pill">Steady</span>`}</div></div>
        <div>${spark(it.prices, 120, 52, 4)}<div class="hint" style="text-align:right;font-size:12px">${it.prices.length} prices seen</div></div></div>
        <div class="note ${cls === "good" ? "ok" : cls === "warn" ? "warn" : ""}"><b>${esc(head)}.</b> ${esc(why)}</div>
        <div class="act" style="display:flex;gap:8px"><button class="btn pay small" data-buy="${esc(it.id)}">Buy</button><button class="btn ghost small" data-ask="Can I afford the ${esc(it.name.toLowerCase())}?">Ask about it</button></div></section>`; }).join("")
      || `<div class="panel">Nothing in your carts. Shop with the ContextIQ extension and items show up here.</div>`}</div>
    ${recs.items.filter((r) => r.id === "plan" || r.id === "wait_price").length ? `<div class="panel-title" style="margin-top:26px"><h2>Recommended</h2></div><div class="feed">${recs.items.filter((r) => r.id === "plan" || r.id === "wait_price").map(recHtml).join("")}</div>` : ""}`;
  animateIn(app); bindPage(); bindRecs(app);
  app.querySelectorAll("[data-buy]").forEach((b) => b.onclick = () => buyWatched(b.dataset.buy));
};

/* ------------------------------------------------------------------ budget */
views.budget = async () => {
  const [h, b, recs] = await Promise.all([loadInsights(), api("/api/budget"), api("/api/recommendations")]);
  const pace = h.cards.find((c) => c.id === "budget-pace")?.numbers || {};
  const total = b.total_budget || 0, spent = b.month_spent, frac = total ? spent / total : 0;
  const cats = Object.entries(b.by_category), top = Math.max(1, ...cats.map(([, v]) => v));
  const realBal = b.available_balance != null ? Number(b.available_balance) : 1450.0;
  const billsTot = b.bills_total != null ? Number(b.bills_total) : (b.bills_before_payday || []).reduce((s, x) => s + x.amount, 0);
  const freeCash = b.free_cash != null ? Number(b.free_cash) : Math.round((realBal - billsTot) * 100) / 100;
  const monthlyInc = b.monthly_income != null ? Number(b.monthly_income) : 4000.0;

  app.innerHTML = `${backBtnHtml("home")}
    <div class="page-head enter">
      <div>
        <h1>Budget & Cash Flow</h1>
        <p class="muted">Where your money is going this month, grounded in your real funds in hand, upcoming bills, and expected salary inflow.</p>
      </div>
    </div>
    
    <div class="panel enter" style="margin-bottom:20px;background:linear-gradient(135deg,var(--navy),#0A5BC4);color:#fff">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px">
        <div>
          <span style="font-size:12px;font-weight:700;letter-spacing:.03em;opacity:.85;text-transform:uppercase">Actual Account Balance</span>
          <div style="font-size:36px;font-weight:800;letter-spacing:-.02em" class="num">${money(realBal)}</div>
          <small style="opacity:.85">Real cash in account · <button class="bb-edit" id="budgetEditBal">Edit Balance</button></small>
        </div>
        <div style="text-align:right">
          <span style="font-size:12px;font-weight:700;letter-spacing:.03em;opacity:.85;text-transform:uppercase">Safe to Spend Now</span>
          <div style="font-size:36px;font-weight:800;color:var(--gold)" class="num">${money(freeCash)}</div>
          <small style="opacity:.85">After ${money(billsTot)} in bills before payday</small>
        </div>
      </div>
      <div class="flow-bar" style="margin-top:16px;background:rgba(255,255,255,.14)">
        ${I.spark}
        <span><b>Money Flow Consideration:</b> Next salary inflow of <b>+${money(monthlyInc)}</b> arrives on <b>${fmtDate(b.next_payday)}</b>. ContextIQ keeps your calculations grounded in your real balance (<b>${money(realBal)}</b>) rather than treating future salary as money already in hand.</span>
      </div>
    </div>

    <div class="grid">
      <div>
        <section class="panel enter">
          <div class="bal-label">Target Monthly Budget Ceiling</div>
          <div class="bal num" id="bspent">${money(0)}</div>
          <p class="hint">of ${money(total)} target limit · next payday ${fmtDate(b.next_payday)}</p>
          <div class="ringrow">
            <div class="ring">${ringSvg(Math.min(1, frac), frac > 1 ? "fill over" : "fill", 120, 11)}<div class="ring-label"><b>${Math.round(frac * 100)}%</b><span>of budget</span></div></div>
            <div class="cats">${cats.map(([k, v]) => { const lim = b.category_budgets[k]; return `<div class="cat"><div class="cat-top"><span>${esc(cap(k))}${lim ? ` <span class="hint">/ ${money(lim, undefined, 0)}</span>` : ""}</span><span class="num" style="${lim && v > lim ? "color:var(--coral)" : ""}">${money(v, undefined, 0)}</span></div>
              <div class="cat-bar"><i data-w="${(v / top * 100).toFixed(0)}%" style="${lim && v > lim ? "background:var(--coral)" : ""}"></i></div></div>`; }).join("")}</div>
          </div>
          ${pace.projected ? paceBar(pace.spent, pace.projected, pace.budget) : ""}
        </section>
        <section class="panel enter" style="animation-delay:.1s">
          <h2>Plan a purchase</h2>
          <p class="hint">Slide to see what a purchase does to your actual cash balance and bills before payday.</p>
          <input type="range" id="wamt" min="10" max="${Math.max(500, Math.round(realBal))}" step="5" value="150" style="width:100%;accent-color:var(--blue)">
          <div class="num" style="font-size:24px;font-weight:800" id="wval">${money(150)}</div>
          <div class="note" id="wres">…</div>
        </section>
      </div>
      <div>
        <div class="panel-title"><h2>What to do</h2></div>
        <div class="stack">${recs.items.map(recHtml).join("")}</div>
        <section class="panel enter" style="margin-top:20px">
          <div class="panel-title"><h2>Coming up before payday</h2><button class="link" id="checkBillsFromBudget">Check all bills ›</button></div>
          <div class="bills">${b.bills_before_payday.map((x) => `<div class="bill"><div class="viz"><div class="tile">${I.calendar}</div></div><div><b>${esc(x.title)}</b><small>${fmtDate(x.due)}</small></div><div class="bill-r num">${money(x.amount)}</div></div>`).join("") || `<p class="hint">No bills before payday.</p>`}</div>
        </section>
      </div>
    </div>`;
  animateIn(app); bindRecs(app);
  countUp($("#bspent"), spent, (v) => money(v));
  $("#budgetEditBal") && ($("#budgetEditBal").onclick = () => editBalance(realBal));
  $("#checkBillsFromBudget") && ($("#checkBillsFromBudget").onclick = openBillsManager);
  let t = null;
  const upd = () => { const a = Number($("#wamt").value); $("#wval").textContent = money(a); clearTimeout(t);
    t = setTimeout(async () => { const r = await api(`/api/whatif?amount=${a}`); $("#wres").className = `note ${r.verdict === "ok" ? "ok" : r.verdict === "wait" ? "warn" : ""}`; $("#wres").textContent = r.message.replace(/(\d{4})-(\d{2})-(\d{2})/, (m) => fmtDate(m + "T12:00")); }, 180); };
  $("#wamt").oninput = upd; upd();
};

/* ------------------------------------------------------------------ invest */
const SCHEME = {
  "Savings / emergency fund": "Cash you can reach in a day. Build 3–6 months of expenses here before anything else.",
  "Short-term deposits or debt funds": "Small ups and downs, steady growth. Suits money you'll need in 1–3 years.",
  "Balanced / hybrid funds": "A mix of shares and bonds — smoother than shares alone. Suits 3–5 years.",
  "Broad equity index funds": "A slice of the whole market. Grows most over 5+ years but can fall in any single year.",
};
views.invest = async () => {
  const [recs] = await Promise.all([api("/api/recommendations"), loadInsights()]);
  const amt = Math.max(10, Math.round((recs.investable || 200) / 2 / 10) * 10);
  app.innerHTML = `${backBtnHtml("home")}
    <div class="page-head enter"><div><h1>Invest and save</h1><p class="muted">Only money you won't need for bills before payday. ContextIQ explains options; it never invests for you.</p></div></div>
    <div class="grid">
      <div>
        <section class="panel enter"><div class="bal-label">Safe to put away now</div><div class="bal num" id="inv">${money(0)}</div>
          <p class="hint">After your upcoming bills and a small cushion. ${recs.spare > 0 ? `You're also on track to finish ${money(recs.spare, undefined, 0)} under budget.` : ""}</p>
          <label class="field">Amount<input type="number" id="iamt" value="${amt}" min="10" step="10"></label>
          <div class="seg" role="group" aria-label="How long"><button data-h="12" aria-pressed="true">About a year</button><button data-h="60" aria-pressed="false">5+ years</button></div></section>
        <section class="panel enter" style="animation-delay:.1s">${recs.items.filter((r) => r.id === "payday_save").map((r) => `<h3>${esc(r.title)}</h3><p class="hint" style="margin:0">${esc(r.body)}</p>`).join("") || ""}</section>
      </div>
      <div><div class="panel-title"><h2>Options for this money</h2></div><div class="stack" id="opts"></div><p class="hint" id="disc" style="margin-top:12px"></p></div>
    </div>`;
  countUp($("#inv"), recs.investable || 0, (v) => money(v));
  let horizon = 12;
  const load = async () => {
    const r = await api("/api/invest", { body: { amount: Number($("#iamt").value) || 0, horizon_months: horizon } });
    if (!r.enabled) { $("#opts").innerHTML = `<div class="panel">${esc(r.message)}</div>`; return; }
    const max = Math.max(...r.options.map((o) => o.p90));
    $("#opts").innerHTML = `<div class="note ${r.liquidity.status === "ok" ? "ok" : "warn"}">${esc(r.liquidity.message)}</div>` + r.options.map((o, j) => `<article class="panel enter" style="animation-delay:${j * 0.08}s">
      <h3>${esc(o.bucket)}</h3><p class="hint">${esc(SCHEME[o.bucket] || "")}</p>
      <div class="range"><i style="left:${(o.p10 / max * 100).toFixed(1)}%;width:${((o.p90 - o.p10) / max * 100).toFixed(1)}%"></i><b style="left:${(o.median / max * 100).toFixed(1)}%"></b></div>
      <div class="pacekey"><span style="--c:#9CC0EE">Likely range after ${o.years >= 2 ? Math.round(o.years) + " years" : "a year"}: ${money(o.p10, undefined, 0)} – ${money(o.p90, undefined, 0)}</span><span style="--c:var(--ink)">Typical ${money(o.median, undefined, 0)}</span><span>Chance of ending lower: ${Math.round(o.chance_of_loss * 100)}%</span></div></article>`).join("");
    $("#disc").textContent = r.disclaimer;
  };
  app.querySelectorAll("[data-h]").forEach((b) => b.onclick = () => { horizon = Number(b.dataset.h); app.querySelectorAll("[data-h]").forEach((x) => x.setAttribute("aria-pressed", x === b)); load(); });
  let t; $("#iamt").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  load();
};

/* ------------------------------------------------------------------ history (briefcase underneath) */
const STATE = { captured: ["Paid", "good"], refunded: ["Refunded", ""], partially_refunded: ["Part refunded", ""], created: ["Not paid", "warn"], approved: ["Approved", "warn"], failed: ["Failed", "warn"] };
function rowHtml(c) {
  const st = STATE[c.payment_state] || [cap(c.payment_state), ""];
  return `<button class="row" data-case="${esc(c.id)}"><span class="tile">${c.channel === "invoice" ? I.doc : c.channel === "bill" ? I.bolt : I.box}</span>
    <span><b>${esc(c.title)}</b><small>${esc(c.merchant)} · ${fmtDate(c.created_at)}</small></span>
    <span class="amt num">${money(c.amount, c.currency)}<br><span class="pill ${st[1]}">${st[0]}</span></span></button>`;
}
views.history = async () => {
  const [list] = await Promise.all([api("/api/cases"), loadInsights()]);
  let acct = S.histAcct || S.home.context.account;
  const draw = () => {
    const rows = list.filter((c) => c.purpose === acct);
    const groups = {};
    rows.forEach((c) => { const k = new Date(c.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" }); (groups[k] ||= []).push(c); });
    $("#hist").innerHTML = Object.entries(groups).map(([k, cs]) => `<section class="panel enter"><div class="panel-title"><h2>${esc(k)}</h2><span class="hint num">${money(cs.reduce((s, c) => s + c.amount, 0))}</span></div>
      <div class="rows">${cs.map(rowHtml).join("")}</div></section>`).join("") || `<div class="panel">No ${acct} purchases yet.</div>`;
    app.querySelectorAll("[data-acct-h]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.acctH === acct));
    bindPage();
  };
  app.innerHTML = `${backBtnHtml("home")}
    <div class="page-head enter"><div><h1>History</h1><p class="muted">Each purchase keeps its receipt, the store's terms and its deadlines — open one to see them.</p></div>
    <div class="seg" style="width:260px" role="group" aria-label="Account"><button data-acct-h="personal">Personal</button><button data-acct-h="business">Business</button></div></div>
    <div id="hist" style="display:grid;gap:20px"></div>`;
  app.querySelectorAll("[data-acct-h]").forEach((b) => b.onclick = () => { acct = S.histAcct = b.dataset.acctH; draw(); });
  draw();
};

views.notices = async () => {
  const [notices, profile] = await Promise.all([
    api("/api/notices").catch(() => []),
    api("/api/profile").catch(() => ({}))
  ]);
  
  const draw = (list) => {
    const listHtml = list.length ? list.map(n => `
      <div class="enter" style="padding:14px 16px;border:1px solid var(--line);border-radius:12px;margin-bottom:12px;background:var(--paper)">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="badge" style="background:#EBF5FB;color:var(--blue);font-weight:700;padding:3px 8px;border-radius:6px;font-size:11px;text-transform:uppercase">${esc(n.notice_type.replace('_', ' '))}</span>
            <b style="font-size:14px;color:var(--ink)">To: ${esc(n.recipient)}</b>
          </div>
          ${n.amount ? `<span class="num" style="font-weight:700;font-size:15px;color:var(--ink)">${money(n.amount)}</span>` : ''}
        </div>
        <div style="font-size:13.5px;color:var(--ink);margin:8px 0;line-height:1.4">${esc(n.message)}</div>
        <div style="font-size:11.5px;color:var(--muted);display:flex;align-items:center;justify-content:space-between;border-top:1px dashed var(--line);padding-top:8px">
          <span>Sent: ${fmtDate(n.created_at)}</span>
          <span style="color:#1A7F4B;font-weight:600">✓ ${esc(n.status)} (Secure One-Way Channel)</span>
        </div>
      </div>
    `).join('') : '<div class="panel enter">No one-way notices dispatched yet. Send your first reminder or notice below!</div>';
    
    $("#notices-list").innerHTML = listHtml;
  };

  app.innerHTML = `${backBtnHtml("home")}
    <div class="page-head enter">
      <div>
        <h1>1-Way Communications</h1>
        <p class="muted">System-driven autonomous payment advisories, supplier verification notices, and scheduled debit notifications.</p>
      </div>
    </div>

    <div class="note ok enter" style="margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div>
        <b style="font-size:14px;color:#1A7F4B">● Autonomous System Dispatch Engine: ACTIVE</b><br>
        <span class="hint" style="color:var(--ink)">ContextIQ automatically verifies POs against invoices, schedules delivery payment advisories, and reserves liquid funds for upcoming bills without manual effort.</span>
      </div>
      <button type="button" class="btn small primary" id="auto-sweep-btn">⚡ Run System Sweep</button>
    </div>
    
    <div style="display:grid;grid-template-columns:1fr 1.2fr;gap:20px;align-items:start">
      <section class="panel enter">
        <div class="panel-title"><h2>Manual Dispatch (Optional)</h2></div>
        <form id="notice-form" style="display:grid;gap:12px">
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Recipient</label>
            <div style="display:flex;gap:6px;margin-bottom:8px">
              <button type="button" class="btn small outline" id="chip-nova">Nova Parts</button>
              <button type="button" class="btn small outline" id="chip-sb">Personal Contact</button>
            </div>
            <input id="notice-recip" class="field-in" placeholder="e.g. Nova Parts or client@example.com" required style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Notice Type</label>
              <select id="notice-type" style="width:100%;padding:10px 8px;border:1px solid var(--line);border-radius:8px">
                <option value="payment_reminder">Payment Reminder</option>
                <option value="invoice_notice">Invoice Notice</option>
                <option value="payment_request">Payment Request</option>
                <option value="status_update">Status Update</option>
              </select>
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Amount (optional)</label>
              <input id="notice-amt" type="number" step="0.01" class="field-in" placeholder="0.00" style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px">
            </div>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Message / Note</label>
            <textarea id="notice-msg" rows="3" class="field-in" placeholder="Type notice details or payment memo..." required style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px"></textarea>
          </div>
          <button type="submit" class="btn primary wide" id="notice-submit">${I.lock} Dispatch 1-Way Notice</button>
        </form>
      </section>

      <section class="panel enter">
        <div class="panel-title">
          <h2>Dispatched Notices Log</h2>
          <span class="hint" id="notices-count">${notices.length} notices</span>
        </div>
        <div id="notices-list"></div>
      </section>
    </div>`;

  draw(notices);

  $("#auto-sweep-btn").onclick = async () => {
    const btn = $("#auto-sweep-btn");
    btn.disabled = true;
    btn.textContent = "Sweeping...";
    try {
      await api("/api/notices/auto-sweep", { method: "POST" });
      const updated = await api("/api/notices");
      draw(updated);
      $("#notices-count").textContent = `${updated.length} notices`;
      toast("Autonomous sweep complete — all upcoming obligations & bills verified.", "Autonomous Engine");
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ Run System Sweep";
    }
  };

  const f = $("#notice-form");
  $("#chip-nova").onclick = () => {
    $("#notice-recip").value = "Nova Parts (Supplier)";
    $("#notice-amt").value = "1200.00";
    $("#notice-msg").value = "Payment reminder: PO-1042 for $1,200.00 is due tomorrow. ContextIQ verified delivery.";
  };
  $("#chip-sb").onclick = () => {
    $("#notice-recip").value = "Personal Contact";
    $("#notice-msg").value = "Payment update regarding recent transaction.";
  };

  f.onsubmit = async (e) => {
    e.preventDefault();
    const btn = $("#notice-submit");
    btn.disabled = true;
    btn.textContent = "Dispatching...";
    try {
      const res = await api("/api/notices", {
        body: {
          recipient: $("#notice-recip").value.trim(),
          notice_type: $("#notice-type").value,
          amount: parseFloat($("#notice-amt").value) || null,
          message: $("#notice-msg").value.trim(),
        }
      });
      if (res.ok) {
        pushNote("Notice Dispatched", `Sent to ${res.notice.recipient} via One-Way Channel.`);
        notices.unshift(res.notice);
        draw(notices);
        $("#notices-count").textContent = `${notices.length} notices`;
        $("#notice-msg").value = "";
      }
    } catch (err) {
      alert("Error sending notice: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${I.lock} Dispatch 1-Way Notice`;
    }
  };
};

/* Evidence ledger: every fact with who vouches for it, oldest first. */
const SEAL = {
  verified: { name: "Verified", tip: "Comes from PayPal or a signed record" },
  claimed: { name: "Claimed", tip: "Someone said it; not yet proven" },
  inferred: { name: "Inferred", tip: "Worked out by ContextIQ from the facts it cites" },
};
const SRC = { paypal_api: "PayPal", paypal_webhook: "PayPal", contextiq: "ContextIQ", merchant_page: "Store page",
  buyer: "Buyer", seller: "Seller", supplier: "Supplier", refund_expert: "ContextIQ" };
function ledgerHtml(evidence, events, evText) {
  const rows = evidence.map((e) => ({ at: e.at, text: e.summary, prov: e.provenance, src: SRC[e.source] || cap(e.source), hash: e.hash }))
    .concat(events.filter((e) => e.type === "delivered").map((e) => ({ at: e.at, text: evText[e.type], prov: "claimed", src: "Carrier (simulated)" })))
    .sort((a, b) => (a.at || "").localeCompare(b.at || ""));
  if (!rows.length) return "";
  const LIMIT = 6, extra = rows.length - LIMIT;
  const li = (r, i) => `<li class="led-row${i >= LIMIT ? " led-more" : ""}" data-prov="${esc(r.prov)}">
      <span class="seal seal-${esc(r.prov)}" title="${esc(SEAL[r.prov]?.tip || "")}" aria-hidden="true"></span>
      <div class="led-body"><p class="led-text">${esc(r.text)}</p>
        <p class="led-meta"><b class="led-prov">${esc(SEAL[r.prov]?.name || r.prov)}</b> by ${esc(r.src)} · ${fmtDate(r.at)}${r.hash ? ` <span class="led-hash" title="SHA-256 ${esc(r.hash)}">#${esc(r.hash.slice(0, 8))}</span>` : ""}</p></div></li>`;
  return `<section class="ledger" aria-label="Evidence for this purchase">
      <h3 class="ledger-h">Evidence</h3>
      <ol class="led" id="led">${rows.map(li).join("")}</ol>
      ${extra > 0 ? `<button class="btn ghost small led-toggle" type="button" onclick="this.previousElementSibling.classList.add('open');this.remove()">Show ${extra} more</button>` : ""}
    </section>`;
}

const LABEL = { return_window: "Return for a refund", replacement_window: "Free swap if faulty", warranty: "Warranty repair", bill: "Bill", supplier_payment: "Payment due" };
async function openCase(id) {
  const v = await api(`/api/cases/${id}`), c = v.case;
  const now = Date.now();
  const dls = (v.obligations || []).filter((o) => LABEL[o.kind] && o.due_at).map((o) => ({ ...o, days: Math.max(0, Math.ceil((new Date(o.due_at) - now) / 864e5)) })).sort((x, y) => x.days - y.days);
  const ev = (v.events || []).filter((e) => ["case_created", "payment_captured", "shipped", "delivered", "refund_completed", "payment_refunded"].includes(e.type));
  const evText = { case_created: "Bought", payment_captured: "Paid through PayPal", shipped: "Shipped (tracking sent to PayPal)", delivered: "Delivered", refund_completed: "Refunded", payment_refunded: "Refunded" };
  const shipped = (v.events || []).some((e) => e.type === "shipped");
  const excl = (v.policy?.extracted?.exclusions || []).map((x) => "Not returnable: " + x);
  openSheet(`<button class="btn-back small" onclick="sheet.close()">${I.back} Back</button><h2>${esc(c.title)}</h2><p class="muted">${esc(c.merchant)} · <b class="num" style="color:var(--ink)">${money(c.amount, c.currency)}</b> · ${cap(c.purpose)}</p>
    ${dls.length ? `<div style="display:grid;gap:12px;margin:16px 0">${dls.map((o) => `<div style="display:grid;grid-template-columns:64px 1fr;gap:14px;align-items:center">
      <div class="viz">${o.days > 0 ? countdown(o.days, o.kind === "warranty" ? 365 : 30, o.days <= 3 ? "#C0392B" : "#1A7F4B") : `<div class="tile">${I.lock}</div>`}</div>
      <div><b>${LABEL[o.kind]}</b><br><span class="hint">${o.days > 0 ? `Until ${fmtDate(o.due_at)}` : "Closed"}${o.kind === "return_window" && notReturnable(c.title, excl) ? " · only if unopened" : ""}</span></div></div>`).join("")}</div>` : ""}
    ${ledgerHtml(v.evidence || [], ev, evText)}
    ${v.role !== "seller" && (v.evidence || []).some((e) => e.kind === "spending_mandate") ? `<div class="mandate-test">
      <button class="btn outline wide" id="mtest" type="button">Test the signed mandate: let an agent try to overspend</button>
      <div id="mtestbox" aria-live="polite"></div></div>` : ""}
    ${v.role === "seller" && c.paypal_capture_id ? `<div id="disputebox" style="margin:12px 0"></div>` : ""}
    ${v.role === "seller" && c.payment_state === "captured" && !shipped ? `<button class="btn primary wide" id="ship">${I.lock} Mark shipped · send tracking to PayPal</button><div id="shipbox"></div>` : ""}
    ${v.role !== "seller" && c.payment_state === "captured" && c.purpose !== "business" ? `<button class="btn outline wide" id="wrong">Something wrong with it?</button><div id="wrongbox"></div>` : ""}`);
  if ($("#disputebox")) drawDispute(id);
  $("#mtest") && ($("#mtest").onclick = async () => {
    $("#mtest").disabled = true;
    const r = await api(`/api/cases/${id}/mandate/overspend-test`, { method: "POST" });
    $("#mtestbox").innerHTML = r.attempts.map((a) => `<div class="mt-row ${a.allowed ? "allowed" : "blocked"}">
        <b>${a.allowed ? "Allowed" : "Blocked"}:</b> ${esc(a.attempt)} (${money(a.amount, c.currency)} to ${esc(a.payee)}).
        <span class="hint">${esc(cap(a.reason))}.</span></div>`).join("");
  });
  $("#ship") && ($("#ship").onclick = async () => {
    $("#ship").disabled = true;
    const r = await api(`/api/cases/${id}/ship`, { body: {} });
    $("#shipbox").innerHTML = r.ok ? `<div class="note ok">PayPal now has ${esc(r.carrier)} tracking ${esc(r.tracking_number)} on capture ${esc(r.capture_id)}.</div>`
      : `<div class="note bad">${esc(r.error || r.detail || "Could not send tracking")}</div>`;
    if (r.ok) setTimeout(() => openCase(id), 1200); else $("#ship").disabled = false;
  });
  $("#wrong") && ($("#wrong").onclick = async () => {
    const r = await api(`/api/cases/${id}/refund-eligibility?issue=${encodeURIComponent("it stopped working")}`);
    const best = r.options.find((o) => o.permitted);
    const hasSwap = r.options.some((o) => o.name === "request_replacement" && o.permitted);
    const hasRefund = r.options.some((o) => o.name === "request_refund" && o.permitted);
    const hasWarranty = r.options.some((o) => o.name === "warranty_claim" && o.permitted);
    const hasDispute = r.options.some((o) => o.name === "escalate_to_paypal_protection" && o.permitted) || !r.eligible;

    let btns = `<div class="note ok" style="margin-bottom:8px"><b>AI Recommendation:</b> ${esc(best ? best.explanation : r.reason)}</div>`;
    if (hasSwap) btns += `<button class="btn ${best?.name === 'request_replacement' ? 'primary' : 'outline'} wide" id="doswap" style="margin-top:6px">${I.swap} Request Free Swap / Replacement</button>`;
    if (hasRefund) btns += `<button class="btn ${best?.name === 'request_refund' ? 'primary' : 'outline'} wide" id="dorefund" style="margin-top:6px">${I.lock} Ask for PayPal Refund</button>`;
    if (hasWarranty) btns += `<button class="btn outline wide" id="dowarranty" style="margin-top:6px">${I.bell} Claim Warranty Repair</button>`;
    if (hasDispute) btns += `<button class="btn outline wide" id="dodispute" style="margin-top:6px">Prepare a PayPal Purchase Protection case</button>`;

    $("#wrongbox").innerHTML = btns || `<div class="note warn">The store's windows have closed. You can open a PayPal dispute.</div>`;

    $("#doswap") && ($("#doswap").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "request_replacement", issue: "faulty unit - free swap requested" } });
      if (rr.ok) {
        $("#wrongbox").innerHTML = `<div class="note ok"><b>Swap request recorded.</b> ${esc(rr.message)}</div>`;
        pushNote("Swap requested", `${c.title} — waiting for ${c.merchant} to confirm.`);
        setTimeout(() => openCase(id), 1200);
      } else {
        $("#wrongbox").innerHTML = `<div class="note bad">${esc(rr.error || "Could not request swap")}</div>`;
      }
    });

    $("#dowarranty") && ($("#dowarranty").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "warranty_claim", issue: "hardware repair under warranty" } });
      if (rr.ok) {
        $("#wrongbox").innerHTML = `<div class="note ok"><b>Warranty claim recorded.</b> ${esc(rr.message)}</div>`;
        pushNote("Warranty claim", `${c.title} — waiting for ${c.merchant} to confirm.`);
        setTimeout(() => openCase(id), 1200);
      } else {
        $("#wrongbox").innerHTML = `<div class="note bad">${esc(rr.error || "Could not claim warranty")}</div>`;
      }
    });

    $("#dodispute") && ($("#dodispute").onclick = async () => {
      const rr = await api(`/api/cases/${id}/resolution`, { body: { action: "escalate_to_paypal_protection", issue: "buyer protection escalation" } });
      if (rr.ok) {
        $("#wrongbox").innerHTML = `<div class="note ok"><b>Case file ready.</b> ${esc(rr.message)} <a href="${esc(rr.open_url)}" target="_blank" rel="noopener">Open PayPal Resolution Center</a></div>`;
        pushNote("PayPal case", `${c.title} — case file ready; open it on PayPal.`);
      } else {
        $("#wrongbox").innerHTML = `<div class="note bad">${esc(rr.error || "Could not open dispute")}</div>`;
      }
    });

    $("#dorefund") && ($("#dorefund").onclick = async () => {
      const { approval_token } = await api(`/api/cases/${id}/refund/approve`, { method: "POST" });
      const rr = await api(`/api/cases/${id}/refund`, { body: { approval_token, reason: "item problem" } });
      if (rr.ok) { $("#wrongbox").innerHTML = `<div class="note ok">Refund requested through PayPal. It usually lands in 3–5 days.</div>`; pushNote("Refund requested", `${c.title} — ${money(c.amount, c.currency)} back to your PayPal.`); setTimeout(() => openCase(id), 1200); }
      else $("#wrongbox").innerHTML = `<div class="note bad">${esc(rr.error || (rr.reasons || []).join("; "))}</div>`;
    });
  });
}

/* ------------------------------------------------------- PayPal dispute (seller side) */
const REASON = { MERCHANDISE_OR_SERVICE_NOT_RECEIVED: "Item not received", MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED: "Not as described",
  UNAUTHORISED: "Payment not authorised", DUPLICATE_TRANSACTION: "Charged twice" };
const EVTYPE = { PROOF_OF_FULFILLMENT: "proof of fulfillment (tracking)", OTHER: "supporting notes" };
async function drawDispute(id) {
  const box = $("#disputebox");
  const { dispute: d } = await api(`/api/cases/${id}/dispute`);
  if (!d) {
    const rd = await api(`/api/cases/${id}/dispute-readiness`).catch(() => null);
    const fix = rd?.proofs.find((p) => !p.present && p.fix);
    box.innerHTML = `${rd ? `<div class="ready">
        <div class="ready-top"><b>Dispute readiness</b><span>${rd.have} of ${rd.of} proofs on file</span></div>
        <div class="meter" role="img" aria-label="${rd.have} of ${rd.of} proofs on file">${rd.proofs.map((p) => `<i class="${p.present ? "on" : ""}" title="${esc(p.label)}"></i>`).join("")}</div>
        <p class="hint">${fix ? esc(fix.fix) + "." : "If the buyer opens a PayPal case, the response is already backed."}</p></div>` : ""}
      <button class="btn outline wide" id="dsync">Check PayPal for disputes on this payment</button>`;
    $("#dsync").onclick = async () => { $("#dsync").disabled = true; await api("/api/disputes/sync", { method: "POST" }); drawDispute(id); };
    return;
  }
  const outcome = d.dispute_outcome?.outcome_code;
  const won = outcome === "RESOLVED_SELLER_FAVOUR";
  const status = d.status === "RESOLVED" ? (won ? "Closed in your favour" : "Closed for the buyer") : "Open: PayPal is waiting on you";
  box.innerHTML = `<div class="dispute-head ${d.status === "RESOLVED" ? (won ? "won" : "lost") : "open"}">
      <span class="dh-dot" aria-hidden="true"></span>
      <div><b>PayPal dispute: ${esc(REASON[d.reason] || d.reason)}</b><p>${esc(status)} · case ${esc(d.dispute_id)}</p></div></div>
    ${d.status !== "RESOLVED" ? `<button class="btn primary wide" id="ddraft">Prepare a response from the briefcase</button><div id="ddraftbox"></div>` : ""}`;
  $("#ddraft") && ($("#ddraft").onclick = async () => {
    $("#ddraft").hidden = true;
    const r = await api(`/api/cases/${id}/dispute/draft`, { method: "POST" });
    if (!r.ok) return ($("#ddraftbox").innerHTML = `<div class="note bad">${esc(r.error)}</div>`);
    const fight = r.recommendation === "fight";
    const have = r.proofs.filter((p) => p.present).length;
    const dd = r.dispute, amt = dd.dispute_amount;
    $("#ddraftbox").innerHTML = `<div class="casefile">
        <div class="cf-col cf-claim">
          <h4>What the buyer told PayPal</h4>
          <p class="cf-big">${esc(REASON[dd.reason] || (dd.reason || "").replaceAll("_", " ").toLowerCase())}</p>
          <p class="muted">${amt ? `${money(Number(amt.value), amt.currency_code)} disputed · ` : ""}case ${esc(dd.dispute_id)}</p>
        </div>
        <div class="cf-col cf-proof">
          <h4>What the briefcase proves</h4>
          <ol class="proofs" aria-label="${have} of ${r.proofs.length} proofs found">${r.proofs.map((p) =>
            `<li class="${p.present ? "has" : "missing"}"><span aria-hidden="true"></span>${esc(p.label)}${p.present ? "" : " <em>(missing)</em>"}</li>`).join("")}</ol>
          <div class="meter" role="img" aria-label="Evidence strength ${have} of ${r.proofs.length}">${r.proofs.map((p) => `<i class="${p.present ? "on" : ""}"></i>`).join("")}</div>
        </div>
      </div>
      <div class="verdict ${fight ? "fight" : "accept"}">
        <b>${fight ? "Respond with evidence" : "Accept and refund"}</b>
        <p>${esc(cap(r.why))}.</p>
        ${r.payload.evidences.map((e) => `<p class="hint">Goes to PayPal as ${esc(EVTYPE[e.evidence_type] || e.evidence_type)}.</p>`).join("")}
      </div>
      <p class="hint cf-why">Card chargebacks alone are forecast to cost $33.79 billion worldwide in 2025
        (<a href="https://www.mastercard.com/hk/en/news-and-trends/Insights/2025/what-s-the-true-cost-of-a-chargeback-in-2025.html" target="_blank" rel="noopener">Mastercard</a>).
        Answering with evidence gathered at the time of sale is how sellers keep that money.</p>
      ${r.payload.evidences.length ? `<button class="btn ${fight ? "primary" : "outline"} wide" id="dsubmit">Send this evidence to PayPal</button>
        <p class="hint cf-promise">Nothing is sent until you press this, and only this exact draft is sent.</p>` : ""}
      <button class="btn ${fight ? "ghost" : "primary"} wide" id="daccept">Accept the claim and refund the buyer</button>
      <div id="dresult"></div>`;
    $("#dsubmit") && ($("#dsubmit").onclick = async () => {
      const s = await api(`/api/cases/${id}/dispute/submit`, { body: { draft_hash: r.draft_hash } });
      $("#dresult").innerHTML = s.ok ? `<div class="note ok">Sent to PayPal: ${esc(s.submitted.join(", "))}.</div>
          ${S.config.paypal_env !== "live" ? `<button class="btn outline wide" id="ddecide">Sandbox: ask PayPal to decide</button>` : ""}`
        : `<div class="note bad">${esc(s.error)}</div>`;
      $("#ddecide") && ($("#ddecide").onclick = async () => {
        const x = await api(`/api/cases/${id}/dispute/sandbox-decide`, { body: { outcome: "SELLER_FAVOR" } });
        if (!x.ok) return ($("#dresult").innerHTML += `<div class="note bad">${esc(x.error)}</div>`);
        if (x.outcome) return drawDispute(id);
        $("#dresult").innerHTML = `<div class="note">PayPal's sandbox is deciding; this usually takes a minute or two. The result arrives by webhook.</div>
          <button class="btn outline wide" id="drefresh">Check PayPal again</button>`;
        $("#drefresh").onclick = async () => { await api("/api/disputes/sync", { method: "POST" }); drawDispute(id); };
      });
    });
    $("#daccept").onclick = async () => {
      const { approval_token } = await api(`/api/cases/${id}/refund/approve`, { method: "POST" });
      let a = await api(`/api/cases/${id}/dispute/accept`, { body: { approval_token } });
      if (a.gateway === "step_up") {
        const code = prompt(`Confirm it's you (${a.reasons.join(", ")}).
Demo delivery of the code: ${a.step_up_code_demo}`);
        if (!code) return;
        a = await api(`/api/cases/${id}/dispute/accept`, { body: { approval_token, step_up_code: code } });
      }
      $("#dresult").innerHTML = a.ok ? `<div class="note ok">Claim accepted on PayPal; the buyer is refunded.</div>` : `<div class="note bad">${esc(a.error || (a.reasons || []).join("; "))}</div>`;
      if (a.ok) setTimeout(() => openCase(id), 1200);
    };
  });
}

/* ------------------------------------------------------------------ assistant */
function openAssistant(q) {
  $("#assistant").hidden = false; $("#askfab").hidden = true;
  if (!S.chat.length) {
    const sug = suggestionsLocal();
    S.chat.push({ text: `Hi ${S.profile.name.split(" ")[0]}! Ask me anything about your carts, purchases, bills, budget, app features, or 1-way notices to people.`, suggestions: sug });
  }
  drawChat();
  if (q) ask(q); else $("#q").focus();
}
function suggestionsLocal() {
  const out = [];
  for (const c of S.cards.slice(0, 5)) { const q = ASK_ABOUT[c.kind]?.(c); if (q) out.push(q); }
  out.push("How's my budget looking?", "What bills are coming up?", "Send a notice to Nova Parts", "Explain ContextIQ features");
  return [...new Set(out)].slice(0, 4);
}
$("#askfab").onclick = () => openAssistant();
$("#asclose").onclick = () => { $("#assistant").hidden = true; $("#askfab").hidden = false; };
$("#askf").onsubmit = (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) { $("#q").value = ""; ask(q); } };
async function ask(q, speak = false) {
  if ($("#assistant").hidden) { $("#assistant").hidden = false; $("#askfab").hidden = true; }
  S.chat.push({ you: true, text: q }, { typing: true }); drawChat();
  try {
    const r = await api("/api/chat", { body: { message: q } });
    S.chat.pop(); S.chat.push({ text: r.answer, case_id: r.proposal?.case_id, action: r.action, suggestions: r.suggestions });
    if (speak) say(r.answer);
  } catch (e) { S.chat.pop(); S.chat.push({ text: e.message }); }
  drawChat();
}
function shortAnswer(t) {
  const parts = String(t).match(/[^.!?]+[.!?]+(\s|$)/g) || [t];
  if (t.length < 260 || parts.length <= 3) return esc(t);
  return `${esc(parts.slice(0, 3).join(""))}<details style="margin-top:6px"><summary class="hint" style="cursor:pointer">More</summary>${esc(parts.slice(3).join(""))}</details>`;
}
function drawChat() {
  const log = $("#log");
  log.innerHTML = S.chat.map((m) => m.typing ? `<div class="bubble ciq typing" aria-label="Thinking"><span></span><span></span><span></span></div>`
    : `<div class="bubble ${m.you ? "you" : "ciq"} enter">${m.you ? esc(m.text) : shortAnswer(m.text)}
      ${m.case_id ? `<div><button class="btn outline small" style="margin-top:8px" data-case="${esc(m.case_id)}">Review and confirm</button></div>` : ""}
      ${m.action?.cart_item ? `<div><button class="btn primary small" style="margin-top:8px" data-item="${esc(m.action.cart_item)}">${esc(m.action.label)}</button></div>` : ""}
      ${m.action?.go ? `<div><button class="btn primary small" style="margin-top:8px" data-go="${esc(m.action.go)}">${esc(m.action.label || "View")}</button></div>` : ""}</div>`).join("");
  const lastSug = [...S.chat].reverse().find((m) => !m.you && m.suggestions)?.suggestions || [];
  $("#sugg").innerHTML = lastSug.map((s) => `<button class="chip" data-q="${esc(s)}">${esc(s)}</button>`).join("");
  $("#sugg").querySelectorAll("[data-q]").forEach((b) => b.onclick = () => ask(b.dataset.q));
  log.querySelectorAll("[data-case]").forEach((b) => b.onclick = () => openCase(b.dataset.case));
  log.querySelectorAll("[data-item]").forEach((b) => b.onclick = () => go("cart").then(() => buyWatched(b.dataset.item)));
  log.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => { $("#assistant").hidden = true; $("#askfab").hidden = false; go(b.dataset.go); });
  log.scrollTop = log.scrollHeight;
}
function say(text) { if (!("speechSynthesis" in window)) return; const u = new SpeechSynthesisUtterance(text); u.lang = navigator.language || "en-US"; speechSynthesis.cancel(); speechSynthesis.speak(u); }
function setupVoice() {
  const btn = $("#mic"), SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { btn.onclick = () => toast("Voice works in Chrome, Edge or Safari.", "Voice"); return; }
  const rec = new SR(); rec.lang = navigator.language || "en-US";
  rec.onresult = (e) => {
    const text = e.results[0][0].transcript;
    if (/\b(pay|send|transfer|approve|confirm)\b/i.test(text) && !/\b(did|was|is|status|can i|should)\b/i.test(text)) {
      const m = "For your safety, I can't pay, send or approve anything by voice. Please confirm it on screen."; toast(m, "Voice"); say(m); return; }
    ask(text, true);
  };
  rec.onend = () => btn.setAttribute("aria-pressed", "false");
  rec.onerror = () => { btn.setAttribute("aria-pressed", "false"); toast("Tap the microphone and try again.", "I didn't catch that"); };
  btn.onclick = () => { btn.setAttribute("aria-pressed", "true"); try { rec.start(); } catch { rec.stop(); } };
}

/* ------------------------------------------------------------------ settings */
$("#me").onclick = () => {
  const p = S.profile;
  openSheet(`<button class="btn-back small" onclick="sheet.close()">${I.back} Back</button>
    <h2>${esc(p.name)}</h2><p class="muted">${esc({ personal: "Personal account", business: "Business account", both: `Personal + ${p.business_name || "business"}` }[p.uses])}</p>
    
    <div class="note ok" style="margin:14px 0">
      <div style="display:flex;align-items:center;justify-content:space-between">
        <b>Linked PayPal Account:</b>
        <span class="pill good">● Live Sandbox Connected</span>
      </div>
      <code style="display:block;margin-top:6px;font-family:monospace;font-size:13.5px;font-weight:700">${esc(p.paypal_email || "sb-hfln853812063@personal.example.com")}</code>
      <div class="hint" style="margin-top:4px;color:#166534">Pre-fills automatically during PayPal checkout · Connected to Alex Rivera</div>
    </div>

    <div class="note">
      Available Cash: ${money(p.available_balance || 1450)} · Payday: day ${esc(p.pay_day)} of the month<br>
      Budget Target: ${money(p.monthly_budget, undefined, 0)} a month · Income: ${money(p.monthly_income, undefined, 0)}/mo<br>
      Location: ${p.location_ok ? "on (travel mode and unusual-place checks)" : "off — going by time of day"}
    </div>
    <button class="btn primary wide" id="redo">Change my setup</button>
    ${S.config && S.config.reset_allowed ? `<button class="btn outline wide" id="reset-all-btn" style="margin-top:10px;border-color:#EF4444;color:#DC2626">⚠️ Reset Everything to Clean Seed</button>` : ""}`);
  $("#redo").onclick = () => { sheet.close(); onboarding(); };
  if ($("#reset-all-btn")) $("#reset-all-btn").onclick = async () => {
    if (confirm("Reset ContextIQ state back to clean initial seed? All test payments, notices, and cart state will be restored to clean baseline.")) {
      sheet.close();
      const r = await api("/api/reset", { method: "POST" });
      toast(r.message || "Reset complete!", "Reset");
      setTimeout(() => location.reload(), 500);
    }
  };
};

/* ------------------------------------------------------------------ shell */
function setChrome(on) { $("#nav").hidden = !on; $("#askfab").hidden = !on || !$("#assistant").hidden; if (!on) $("#assistant").hidden = true; }
const SKELETON = `<div class="skel" aria-busy="true" aria-label="Loading">
  <div class="skel-line w40"></div><div class="skel-line w60"></div>
  <div class="skel-grid"><div class="skel-card"></div><div class="skel-card"></div><div class="skel-card"></div></div></div>`;
async function go(name) {
  name = { pay: "cart", activity: "history" }[name] || name;
  if (S.tab && S.tab !== name) S.prevTab = S.tab;
  setChrome(true); S.tab = name;
  document.querySelectorAll(".links [data-tab]").forEach((b) => b.removeAttribute("aria-current"));
  document.querySelector(`.links [data-tab="${name}"]`)?.setAttribute("aria-current", "page");
  history.replaceState(null, "", `#${name}`);
  app.innerHTML = SKELETON;
  try { await views[name](); } catch (e) { app.innerHTML = `<h1>That didn't load</h1><div class="note bad">${esc(e.message)}</div><p class="muted">Check that ContextIQ is running, then reload the page.</p>`; }
  app.focus({ preventScroll: true });
}
document.querySelectorAll(".links [data-tab]").forEach((b) => b.onclick = () => { $("#moremenu").hidden = true; go(b.dataset.tab); });
$("#morebtn").onclick = (e) => { e.stopPropagation(); const m = $("#moremenu"); m.hidden = !m.hidden; $("#morebtn").setAttribute("aria-expanded", String(!m.hidden)); };
document.addEventListener("click", (e) => { if (!e.target.closest(".more-wrap")) { $("#moremenu").hidden = true; $("#morebtn").setAttribute("aria-expanded", "false"); } });
$("#tourbtn").onclick = () => { $("#moremenu").hidden = true; store.set("ciq-tour", "1"); refreshTour(); };

/* ------------------------------------------------------- role: buyer or seller */
function markRole() {
  document.querySelectorAll("#role [data-user]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.user === S.user)));
  document.body.classList.toggle("seller", S.user === "brightmart");
}
async function setUser(u, view) {
  if (u === S.user && !view) return;
  S.user = u; store.set("ciq-user", u);
  Object.assign(S, { chat: [], cart: null, checkout: null, home: null, cards: [] });
  S.profile = await api("/api/profile");
  $("#me").textContent = S.profile.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  markRole();
  if (sheet.open) sheet.close();
  await go(view || S.tab || "home");
  refreshTour();
}
document.querySelectorAll("#role [data-user]").forEach((b) => b.onclick = () => setUser(b.dataset.user));

/* ------------------------------------------------- judge tour: the hero flow, live */
const TOUR = [
  { t: "Pay with PayPal", who: "alex", hint: "Cart → Pay with PayPal, approve in the PayPal popup" },
  { t: "Seller ships", who: "brightmart", hint: "Open the purchase → Mark shipped; tracking goes to PayPal" },
  { t: "Buyer disputes at PayPal", who: "alex", hint: "As the sandbox buyer, report the item as not received" },
  { t: "Answer from the briefcase", who: "brightmart", hint: "Prepare a response, review it, approve & send" },
  { t: "PayPal decides", who: "brightmart", hint: "Sandbox: ask PayPal to decide" },
];
async function tourProgress() {
  const id = store.get("ciq-tour-case");
  if (!id) return { done: 0 };
  const as = { headers: { "X-User-Id": "alex" } };
  try {
    const v = await (await fetch(`/api/cases/${id}`, as)).json();
    if (!v.case) return { done: 0 };
    const ev = new Set((v.events || []).map((e) => e.type));
    const d = (await (await fetch(`/api/cases/${id}/dispute`, as)).json()).dispute;
    let done = v.case.paypal_capture_id ? 1 : 0;
    if (done && ev.has("shipped")) done = 2;
    if (done === 2 && d) done = 3;
    if (done === 3 && ev.has("dispute_evidence_submitted")) done = 4;
    if (done === 4 && d.status === "RESOLVED") done = 5;
    return { done, id, outcome: d?.dispute_outcome?.outcome_code };
  } catch { return { done: 0 }; }
}
let tourTimer;
async function refreshTour() {
  const bar = $("#tour");
  clearInterval(tourTimer);
  if (store.get("ciq-tour") !== "1") { bar.hidden = true; return; }
  const p = await tourProgress();
  const next = TOUR[p.done];
  bar.hidden = false;
  bar.innerHTML = `<div class="tour-in">
      <b class="tour-title">Judge tour</b>
      <ol class="tour-steps">${TOUR.map((s, i) => `<li class="${i < p.done ? "done" : i === p.done ? "now" : ""}"><span>${i < p.done ? "✓" : i + 1}</span>${esc(s.t)}</li>`).join("")}</ol>
      <div class="tour-next">${next ? `<span class="tour-hint">${esc(next.hint)}</span>
        <button class="btn primary tour-go" id="tourgo">${esc(next.who === S.user ? "Go" : `Switch to ${next.who === "alex" ? "buyer" : "seller"}`)}</button>`
        : `<span class="tour-hint ok">PayPal decided: ${esc((p.outcome || "resolved").replaceAll("_", " ").toLowerCase())}</span>`}</div>
      <button class="x tour-x" id="tourx" aria-label="Close the tour">×</button>
    </div>`;
  $("#tourx").onclick = () => { store.set("ciq-tour", null); refreshTour(); };
  if ($("#tourgo")) $("#tourgo").onclick = async () => {
    if (next.who !== S.user) await setUser(next.who);
    if (p.done === 0) return go("cart");
    if (p.done === 2) {
      if (S.config.paypal_env === "mock") { await api(`/api/mock/open-dispute/${p.id}`, { method: "POST" }); return refreshTour(); }
      return window.open("https://www.sandbox.paypal.com/myaccount/activities/", "_blank", "noopener");
    }
    if (p.done === 3) await api("/api/disputes/sync", { method: "POST" }).catch(() => {});
    await go("history"); openCase(p.id);
  };
  if (p.done < 5) tourTimer = setInterval(refreshTour, 15000);
}
function cartFromUrl() {
  const p = new URLSearchParams(location.search).get("cart"); if (!p) return null;
  try { return JSON.parse(decodeURIComponent(escape(atob(p)))); } catch { return null; }
}
(async function init() {
  S.config = await api("/api/config");
  S.profile = await api("/api/profile");
  $("#me").textContent = S.profile.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  setupVoice();
  if (S.profile.location_ok && navigator.geolocation)
    navigator.geolocation.getCurrentPosition((pos) => { S.pos = { lat: pos.coords.latitude, lon: pos.coords.longitude }; }, () => {}, { maximumAge: 900000, timeout: 5000 });
  const qs = new URLSearchParams(location.search);
  markRole();
  if (qs.get("demo") === "1") {
    store.set("ciq-tour", "1");
    if (!S.profile.setup_done) {  // judges skip onboarding; defaults match the seeded profile
      await api("/api/profile/setup", { body: { uses: "both", goals: ["deals"], location_ok: false, monthly_budget: 1900 } });
      S.profile = await api("/api/profile");
    }
  }
  refreshTour();
  if (!S.profile.setup_done) { onboarding(); return; }
  if (qs.get("approved")) {
    S.checkout = JSON.parse(sessionStorage.getItem("ciq-checkout") || "null");
    await go("home"); if (S.checkout) { openSheet(`<ul class="steps"><li class="done">Approved on PayPal</li><li class="now">Completing payment</li></ul>`); complete(); }
    return;
  }
  const cart = cartFromUrl(), hash = location.hash.slice(1);
  await go(views[hash] ? hash : cart ? "pay" : "home");
  if (cart) startPay(cart);
})();
