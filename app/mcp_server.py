"""ContextIQ as an MCP server, so MCP-capable assistants (e.g. Claude Desktop) can use it as a tool.

Run:  python -m app.mcp_server        (stdio transport)
Claude Desktop config:  {"mcpServers": {"contextiq": {"command": "python", "args": ["-m", "app.mcp_server"],
                          "cwd": "<path to contextiq>", "env": {"CONTEXTIQ_USER": "alex"}}}}

Every tool goes through the plugin registry (scopes, rate limits, audit). Tools can read and propose;
none can capture, refund or pay — those exist only behind the security gateway with on-screen approval.
"""
from __future__ import annotations

import os

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import plugins
from .db import init_db, session_scope

mcp = _Server("ContextIQ")
USER = os.getenv("CONTEXTIQ_USER", "alex")


def _with_db(fn):
    def run(**kw):
        with session_scope() as db:
            return fn(db, **kw)
    return run


@mcp.tool()
def list_purchases() -> list[dict]:
    """List the user's purchases with their payment state."""
    from .agents import helpdesk
    return plugins.call("contextiq.cases", "list_purchases", USER, {}, _with_db(lambda db: helpdesk.list_cases(db, USER)))


@mcp.tool()
def get_purchase(case_id: str) -> dict:
    """The user's view of one purchase: agreement, evidence (with provenance), deadlines and timeline."""
    from . import briefcase as bc
    return plugins.call("contextiq.cases", "get_purchase", USER, {"case_id": case_id},
                        _with_db(lambda db, case_id: bc.view_case(db, case_id, USER) or {"error": "not found"}))


@mcp.tool()
def check_refund_eligibility(case_id: str, issue: str) -> dict:
    """Is a refund/replacement/warranty claim possible for this purchase? Read-only."""
    from .agents import commerce
    from .models import Case

    def impl(db, case_id, issue):
        r = commerce.refund_eligibility(db, db.get(Case, case_id), issue)
        return {"eligible": r["eligible"], "reason": r["reason"], "best_option": (r["decision"]["choice"] or {}).get("name")}
    return plugins.call("contextiq.refunds", "check_refund_eligibility", USER, {"case_id": case_id, "issue": issue}, _with_db(impl))


@mcp.tool()
def budget_status() -> dict:
    """This month's spending, budget left and bills before payday."""
    from .agents import budget
    return plugins.call("contextiq.budget", "budget_status", USER, {}, _with_db(lambda db: budget.status(db, USER)))


@mcp.tool()
def can_i_afford(amount: float) -> dict:
    """Buy-now vs wait-until-payday check for a purchase amount."""
    from .agents import budget
    return plugins.call("contextiq.budget", "can_i_afford", USER, {"amount": amount},
                        _with_db(lambda db, amount: budget.what_if(db, USER, amount)))


@mcp.tool()
def assess_payment_request(payee: str, amount: float, message: str) -> dict:
    """Warning signs in a payment request (scam patterns). Signals, not proof."""
    from .agents import context
    return plugins.call("contextiq.risk", "assess_payment_request", USER, {"payee": payee, "amount": amount, "message": message},
                        _with_db(lambda db, payee, amount, message: context.assess_risk(db, USER, payee, amount, text=message)))


@mcp.tool()
def list_disputes_for_me() -> list[dict]:
    """PayPal disputes on this user's sales, synced from PayPal's Disputes API and matched to purchases."""
    from .agents import dispute_response
    return plugins.call("contextiq.disputes", "list_disputes_for_me", USER, {},
                        _with_db(lambda db: [d for d in dispute_response.sync(db) if d["case_id"]]))


@mcp.tool()
def draft_dispute_response(case_id: str) -> dict:
    """Draft a PayPal dispute response from the purchase's evidence (tracking, agreed terms) with a
    fight-or-accept recommendation. Read-only: the seller approves and sends it in ContextIQ."""
    from . import briefcase as bc
    from .agents import dispute_response
    from .models import Case

    def impl(db, case_id):
        v = bc.view_case(db, case_id, USER)
        if not v or v["role"] != "seller":
            return {"error": "not found, or you are not the seller on this purchase"}
        d = dispute_response.draft(db, db.get(Case, case_id))
        return d | {"next_step": "Review and approve this draft in ContextIQ; this tool never sends anything."}
    return plugins.call("contextiq.disputes", "draft_dispute_response", USER, {"case_id": case_id}, _with_db(impl))


@mcp.tool()
def ask(question: str) -> str:
    """Ask ContextIQ anything about payments, refunds, bills or budget."""
    from . import orchestrator
    return plugins.call("contextiq.assistant", "ask", USER, {"question": question},
                        _with_db(lambda db, question: orchestrator.handle(db, USER, question)["answer"]))


if __name__ == "__main__":
    init_db()
    mcp.run()
