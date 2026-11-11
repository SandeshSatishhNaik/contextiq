"""Market data for the optional Investment expert — Alpha Vantage (free key: alphavantage.co).

Set ALPHAVANTAGE_API_KEY in .env. Without a key the expert says market data isn't connected and never
invents prices. Everything returned is labelled as a fact (quote, reported fundamentals), a sentiment
signal, or a forecast/scenario — they are kept apart on purpose.
"""
from __future__ import annotations

import os
import time

import httpx

BASE = "https://www.alphavantage.co/query"
_cache: dict[tuple, tuple[float, dict]] = {}
TTL = 15 * 60  # free tier is rate-limited; quotes are cached briefly (never used for payments)


class MarketData:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.key = api_key if api_key is not None else os.getenv("ALPHAVANTAGE_API_KEY", "")
        self.http = httpx.Client(transport=transport, timeout=20)

    @property
    def connected(self) -> bool:
        return bool(self.key)

    def _get(self, **params) -> dict:
        k = tuple(sorted(params.items()))
        hit = _cache.get(k)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
        r = self.http.get(BASE, params=params | {"apikey": self.key})
        r.raise_for_status()
        data = r.json()
        if "Note" in data or "Information" in data:
            raise RuntimeError("market data provider rate limit reached — try again in a minute")
        _cache[k] = (time.time(), data)
        return data

    def quote(self, symbol: str) -> dict:
        q = self._get(function="GLOBAL_QUOTE", symbol=symbol).get("Global Quote", {})
        if not q:
            return {"symbol": symbol, "found": False}
        return {"symbol": symbol, "found": True, "price": float(q["05. price"]), "change_pct": q["10. change percent"],
                "as_of": q["07. latest trading day"], "kind": "fact (market quote)"}

    def fundamentals(self, symbol: str) -> dict:
        o = self._get(function="OVERVIEW", symbol=symbol)
        if not o or "Symbol" not in o:
            return {"symbol": symbol, "found": False}
        num = lambda k: float(o[k]) if o.get(k) not in (None, "None", "-", "") else None  # noqa: E731
        return {"symbol": symbol, "found": True, "name": o.get("Name"), "sector": o.get("Sector"),
                "pe_ratio": num("PERatio"), "profit_margin": num("ProfitMargin"),
                "revenue_growth_yoy": num("QuarterlyRevenueGrowthYOY"), "beta": num("Beta"),
                "kind": "fact (company-reported fundamentals)"}

    def news(self, symbol: str, limit: int = 5) -> dict:
        n = self._get(function="NEWS_SENTIMENT", tickers=symbol, limit=str(limit))
        feed = n.get("feed", [])[:limit]
        scores = [float(a.get("overall_sentiment_score", 0)) for a in feed]
        return {"symbol": symbol, "articles": [{"title": a.get("title"), "source": a.get("source"), "url": a.get("url"),
                                                "time": a.get("time_published")} for a in feed],
                "avg_sentiment": round(sum(scores) / len(scores), 3) if scores else None,
                "kind": "signal (news sentiment) — not a prediction"}


def research(symbol: str, md: MarketData | None = None) -> dict:
    md = md or MarketData()
    if not md.connected:
        return {"connected": False, "message": "Market data isn't connected. Add a free Alpha Vantage key to look up "
                                               "real prices, company figures and news."}
    try:
        f = md.fundamentals(symbol)
        q = md.quote(symbol)
        n = md.news(symbol)
    except Exception as exc:  # noqa: BLE001
        return {"connected": True, "error": str(exc)}
    risks = []
    if f.get("beta") and f["beta"] > 1.3:
        risks.append(f"moves more than the market (beta {f['beta']:.2f})")
    if f.get("pe_ratio") and f["pe_ratio"] > 40:
        risks.append(f"priced high relative to earnings (P/E {f['pe_ratio']:.0f})")
    if f.get("profit_margin") is not None and f["profit_margin"] < 0:
        risks.append("currently loses money")
    if n.get("avg_sentiment") is not None and n["avg_sentiment"] < -0.15:
        risks.append("recent news is mostly negative")
    return {"connected": True, "symbol": symbol, "quote": q, "fundamentals": f, "news": n,
            "risk_flags": risks or ["no obvious red flags in the figures checked"],
            "reminder": "Facts and signals, not a forecast. Nobody can reliably pick tomorrow's winners."}


def diversification(holdings: list[dict]) -> dict:
    """holdings: [{symbol, value, sector}] entered by the user. Concentration measured with the HHI."""
    total = sum(h["value"] for h in holdings) or 1
    by_sector: dict[str, float] = {}
    for h in holdings:
        by_sector[h.get("sector") or "unknown"] = by_sector.get(h.get("sector") or "unknown", 0) + h["value"]
    weights = [v / total for v in by_sector.values()]
    hhi = sum(w * w for w in weights)
    top = max(holdings, key=lambda h: h["value"]) if holdings else None
    notes = []
    if top and top["value"] / total > 0.3:
        notes.append(f"{top['symbol']} is {top['value'] / total:.0%} of your holdings — a single-company risk.")
    if hhi > 0.4:
        notes.append("Most of your money sits in one or two sectors.")
    return {"sector_weights": {k: round(v / total, 3) for k, v in by_sector.items()}, "concentration_index": round(hhi, 3),
            "level": "concentrated" if hhi > 0.4 else "moderate" if hhi > 0.2 else "well spread", "notes": notes}
