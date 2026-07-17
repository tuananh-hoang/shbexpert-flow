"""mcp-deterministic — MCP server exposing pure Python calculation tools.

Allowlist (ai-architecture.md §6.1): Financial, Policy, Collateral agents
connect here. Nothing in this server calls an LLM — every tool is a plain
function with a fixed formula_version, so results are reproducible and
testable (PRD 12.1: 100% of mock calculations must match tolerance).

Phase 2 added `calculate_financial_ratios`; Phase 3 adds `calculate_coverage`
(shared by Financial + Collateral agents). `evaluate_policy_rules` is
deferred — Policy Agent's Phase 3 finding comes from search_policy alone.
"""
# NOTE: deliberately NO `from __future__ import annotations` here.
# mcp==1.12.4's FastMCP tool registration calls `issubclass(param.annotation,
# Context)` on every parameter without resolving PEP 563 stringized
# annotations first — with the future import, `param.annotation` is the
# literal string "float" instead of the `float` class, and issubclass()
# raises `TypeError: issubclass() arg 1 must be a class`. Any @mcp.tool()
# function with typed parameters breaks under that import; verified by
# reproducing the exact traceback with/without it. Keep this file free of
# the future import even though every other module in the repo uses it.
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

SERVER_NAME = "mcp-deterministic"
PORT = 8200

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def ping() -> dict:
    """Health-check tool — confirms the MCP connection works end to end.
    Not part of the real tool allowlist; safe to remove once Phase 2/3
    tools exist and an agent has exercised them at least once."""
    return {"status": "ok", "server": SERVER_NAME}


FORMULA_VERSION = "FIN-0.3-MOCK"


@mcp.tool()
def calculate_financial_ratios(revenue: float, ebitda: float, debt_service_annual: float) -> dict:
    """Pure Python financial ratio calculation — NO LLM involved (overview.md
    nguyên tắc 4: "Tính toán xác định"). The Financial Agent calls this with
    numbers read from ExtractedField rows; the LLM only explains the result
    afterward, never computes it. Every result carries formula_version so
    the eval harness can assert exact-match against a test vector
    (ai-architecture.md §6.3, PRD 12.1: 100% of mock calculations must match
    tolerance).

    Returns dscr (debt service coverage ratio) and ebitda_margin. Extend
    with more ratios (current_ratio, debt_ratio, ...) as later phases need
    them — keep every new ratio a plain formula, never a model call.
    """
    dscr = round(ebitda / debt_service_annual, 3) if debt_service_annual else None
    ebitda_margin = round(ebitda / revenue, 4) if revenue else None
    return {
        "outputs": {"dscr": dscr, "ebitda_margin": ebitda_margin},
        "inputs": {
            "revenue": revenue,
            "ebitda": ebitda,
            "debt_service_annual": debt_service_annual,
        },
        "formula_version": FORMULA_VERSION,
    }


COVERAGE_FORMULA_VERSION = "COL-0.2-MOCK"


@mcp.tool()
def calculate_coverage(eligible_value: float, requested_amount: float) -> dict:
    """Pure Python coverage-ratio calculation. Reused by BOTH Financial and
    Collateral agents (ai-architecture.md §6.1 lists this under the shared
    mcp-deterministic allowlist) — with different `eligible_value` inputs:
    Financial passes the document's face-value valuation (naive, no
    haircut/expiry check); Collateral passes a value it has itself vetted
    (e.g. after checking the certificate hasn't expired). Same formula,
    different diligence upstream — this is deliberate: it is what lets
    Phase 4's conflict detector find a real disagreement on
    issue_key=COLLATERAL_COVERAGE without needing two different formulas.
    """
    coverage_ratio = round(eligible_value / requested_amount, 3) if requested_amount else None
    return {
        "outputs": {"coverage_ratio": coverage_ratio},
        "inputs": {"eligible_value": eligible_value, "requested_amount": requested_amount},
        "formula_version": COVERAGE_FORMULA_VERSION,
    }


async def health(_request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": SERVER_NAME})


# Mount the FastMCP streamable-HTTP app under / and add a plain /health
# route for docker-compose healthchecks (the MCP endpoint itself expects
# MCP-protocol headers, so a bare `curl /mcp` isn't a useful liveness probe).
#
# IMPORTANT: mcp.streamable_http_app() returns a Starlette app whose
# lifespan starts the StreamableHTTPSessionManager's task group
# (`lifespan=lambda app: self.session_manager.run()`). Wrapping that app
# in a *new* outer Starlette app without re-attaching this exact lifespan
# leaves the session manager's task group uninitialized — every POST /mcp
# then 500s with "Task group is not initialized. Make sure to use run()."
# So: call streamable_http_app() first (creates mcp.session_manager as a
# side effect), then explicitly wire the same lifespan into our outer app.
mcp_asgi_app = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp_asgi_app),
    ],
    lifespan=lambda _app: mcp.session_manager.run(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
