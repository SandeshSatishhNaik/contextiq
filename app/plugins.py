"""Secure plugin / tool registry. Every tool — ours or external — is registered with an identity, the
functions it offers, the permission scopes it needs, input schemas, authentication, a rate limit and an
audit requirement. All tool calls (from the orchestrator or from MCP clients) go through `call()`.

Money-moving functions are NOT callable through the registry at all: they exist only behind the
security gateway with explicit user approval.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .db import session_scope
from .models import AuditLog

# scopes a user grants to AI tools; payments:execute is deliberately absent (gateway only)
DEFAULT_GRANTS = {"cases.read", "budget.read", "risk.read", "invoice.read", "policy.read", "market.read", "chat"}


@dataclass
class Plugin:
    id: str
    publisher: str
    functions: dict[str, dict]           # name -> JSON schema of arguments
    scopes: set[str]
    auth: str
    rate_limit_per_min: int
    audit: bool = True
    external: bool = False
    notes: str = ""
    _calls: dict = field(default_factory=lambda: defaultdict(deque))


REGISTRY: dict[str, Plugin] = {}


def register(p: Plugin) -> None:
    REGISTRY[p.id] = p


class PermissionDenied(Exception):
    pass


class RateLimited(Exception):
    pass


def call(plugin_id: str, fn: str, user_id: str, args: dict, impl, grants: set[str] | None = None):
    p = REGISTRY.get(plugin_id)
    if not p or fn not in p.functions:
        raise PermissionDenied(f"{plugin_id}.{fn} is not a registered tool")
    grants = DEFAULT_GRANTS if grants is None else grants
    missing = p.scopes - grants
    if missing:
        _audit(user_id, plugin_id, fn, args, "deny", [f"missing scope(s): {', '.join(sorted(missing))}"])
        raise PermissionDenied(f"missing scope(s): {', '.join(sorted(missing))}")
    required = [k for k in p.functions[fn].get("required", [])]
    if any(k not in args for k in required):
        raise PermissionDenied(f"missing argument(s): {', '.join(k for k in required if k not in args)}")
    q, now = p._calls[user_id], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= p.rate_limit_per_min:
        _audit(user_id, plugin_id, fn, args, "deny", ["rate limit"])
        raise RateLimited(f"{plugin_id} allows {p.rate_limit_per_min} calls per minute")
    q.append(now)
    result = impl(**args)
    if p.audit:
        _audit(user_id, plugin_id, fn, args, "allow", [])
    return result


def _audit(user_id, plugin_id, fn, args, verdict, reasons):
    with session_scope() as db:
        db.add(AuditLog(actor=user_id, action=f"tool:{plugin_id}.{fn}", request={k: str(v)[:80] for k, v in args.items()},
                        verdict=verdict, reasons=reasons))


S = lambda **props: {"type": "object", "properties": {k: {"type": v} for k, v in props.items()},  # noqa: E731
                     "required": list(props)}
register(Plugin("contextiq.cases", "ContextIQ", {"list_purchases": S(), "get_purchase": S(case_id="string")},
                {"cases.read"}, "user session", 60))
register(Plugin("contextiq.refunds", "ContextIQ", {"check_refund_eligibility": S(case_id="string", issue="string")},
                {"cases.read", "policy.read"}, "user session", 30))
register(Plugin("contextiq.budget", "ContextIQ", {"budget_status": S(), "can_i_afford": S(amount="number")},
                {"budget.read"}, "user session", 60))
register(Plugin("contextiq.risk", "ContextIQ", {"assess_payment_request": S(payee="string", amount="number", message="string")},
                {"risk.read"}, "user session", 30))
register(Plugin("contextiq.invoices", "ContextIQ", {"check_invoice": S(po="object", invoice="object")},
                {"invoice.read"}, "user session", 30))
register(Plugin("contextiq.disputes", "ContextIQ",
                {"list_disputes_for_me": S(), "draft_dispute_response": S(case_id="string")},
                {"cases.read"}, "user session", 30))
register(Plugin("contextiq.assistant", "ContextIQ", {"ask": S(question="string")}, {"chat"}, "user session", 30))
register(Plugin("paypal.rest", "PayPal", {"orders": {}, "captures": {}, "refunds": {}, "invoicing": {}, "webhooks": {}},
                {"payments:execute"}, "OAuth 2.0 client credentials (server-side only)", 120, external=True,
                notes="Not callable by AI tools. Only the payment adapter behind the security gateway uses it."))
register(Plugin("alphavantage.market", "Alpha Vantage", {"quote": S(symbol="string"), "fundamentals": S(symbol="string"),
                                                          "news": S(symbol="string")},
                {"market.read"}, "API key (server-side)", 5, external=True))
register(Plugin("llm.reasoning", "Groq or Anthropic", {"complete": S(prompt="string")}, {"chat"}, "API key (server-side)", 30,
                external=True, notes="Language and reasoning only; never sees credentials, never moves money."))
register(Plugin("browser.cart", "ContextIQ extension", {"read_cart": S()}, {"cart.read"}, "user click (activeTab)", 30,
                external=True, notes="Runs only when the user clicks the extension."))


def describe() -> list[dict]:
    return [{"id": p.id, "publisher": p.publisher, "functions": sorted(p.functions), "scopes": sorted(p.scopes),
             "auth": p.auth, "rate_limit_per_min": p.rate_limit_per_min, "audited": p.audit, "external": p.external,
             "callable_by_ai": not ({"payments:execute", "cart.read"} & p.scopes), "notes": p.notes}
            for p in REGISTRY.values()]
