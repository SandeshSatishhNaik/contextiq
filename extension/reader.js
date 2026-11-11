// Injected only when the user clicks the extension (activeTab). Reads the visible cart; never changes the page
// and never inserts affiliate links. Works on pages that mark their cart with data-ciq-* attributes
// (the demo store); for other stores it falls back to a best-effort reader.
(() => {
  const root = document.querySelector("[data-ciq-merchant]");
  if (root) {
    const items = [...document.querySelectorAll("[data-ciq-item]")].map((el) => ({
      name: el.querySelector("[data-ciq-name]").textContent.trim(),
      unit_price: parseFloat(el.querySelector("[data-ciq-price]").textContent),
      quantity: parseInt(el.querySelector("[data-ciq-qty]")?.textContent || "1", 10) || 1,
    }));
    const pol = document.querySelector("[data-ciq-policy]");
    return { merchant: root.dataset.ciqMerchant, seller_id: root.dataset.ciqSeller || null, currency: root.dataset.ciqCurrency || "USD",
      items, policy_text: pol ? [...pol.querySelectorAll("p")].map((p) => p.textContent).join("\n") : "", policy_url: location.href, page_url: location.href };
  }
  // best-effort fallback: price-looking lines near the word "cart"
  const text = document.body.innerText.split("\n").filter((l) => /[$₹€£]\s?\d/.test(l)).slice(0, 10);
  const items = text.map((l) => ({ name: l.replace(/[$₹€£]\s?[\d,.]+/g, "").trim().slice(0, 80) || "Item",
    unit_price: parseFloat((l.match(/[$₹€£]\s?([\d,.]+)/) || [0, "0"])[1].replace(/,/g, "")) })).filter((i) => i.unit_price > 0);
  return { merchant: location.hostname, items, currency: "USD", policy_text: "", page_url: location.href, best_effort: true };
})();
