const API = "http://localhost:8000";
const out = document.getElementById("out");
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const [{ result: cart }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["reader.js"] });
  if (!cart || !cart.items.length) { out.innerHTML = `<p>No cart found on this page.</p>`; return; }
  const { user = "alex" } = await chrome.storage.local.get("user");
  let a;
  try {
    const r = await fetch(`${API}/api/cart/analyze`, { method: "POST", headers: { "Content-Type": "application/json", "X-User-Id": user }, body: JSON.stringify(cart) });
    a = await r.json();
  } catch { out.innerHTML = `<p>ContextIQ isn't running on ${API}. Start it with <code>python run.py</code>.</p>`; return; }
  const price = a.prices.find((p) => p.lowest_seen != null);
  out.innerHTML = `
    <p><strong>${esc(cart.merchant)}</strong> · ${esc(a.currency)} ${a.total.toFixed(2)}${cart.best_effort ? " <span class='muted'>(best-effort read)</span>" : ""}</p>
    ${a.policy ? `<ul>${a.policy.summary.slice(0, 4).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : `<p class="muted">No return policy found on this page.</p>`}
    ${a.policy && a.policy.injection_flags.length ? `<p class="v wait">Ignored hidden instructions found on this page.</p>` : ""}
    <p class="v ${a.budget.verdict === "ok" ? "ok" : "wait"}">${esc(a.budget.message)}</p>
    ${price ? `<p class="muted">Lowest price seen: ${price.lowest_seen.toFixed(2)}${price.is_lowest_seen ? " — this is the lowest so far" : ""}.</p>` : ""}
    <button id="pay">Pay with ContextIQ</button>`;
  document.getElementById("pay").onclick = () => {
    const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(cart))));
    chrome.tabs.create({ url: `${API}/?cart=${encodeURIComponent(b64)}` });
  };
})();
