"""Recorded-shape Alpha Vantage responses for offline tests (values are illustrative)."""
import json

import httpx

DATA = {
    "GLOBAL_QUOTE": {"Global Quote": {"01. symbol": "ACME", "05. price": "123.4500", "07. latest trading day": "2026-11-06",
                                      "10. change percent": "-1.2300%"}},
    "OVERVIEW": {"Symbol": "ACME", "Name": "Acme Corp", "Sector": "TECHNOLOGY", "PERatio": "52.1", "ProfitMargin": "0.12",
                 "QuarterlyRevenueGrowthYOY": "0.08", "Beta": "1.45"},
    "NEWS_SENTIMENT": {"feed": [{"title": "Acme misses estimates", "source": "Example Wire", "url": "https://example.com/a",
                                 "time_published": "20261106T120000", "overall_sentiment_score": "-0.30"},
                                {"title": "Acme launches product", "source": "Example News", "url": "https://example.com/b",
                                 "time_published": "20261105T090000", "overall_sentiment_score": "-0.10"}]},
}


def transport():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(DATA[req.url.params["function"]]).encode())
    return httpx.MockTransport(h)
