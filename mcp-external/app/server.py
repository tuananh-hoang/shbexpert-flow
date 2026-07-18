"""mcp-external — MCP server wrapping the `tools-mock` REST service.

Allowlist (ai-architecture.md §6.1): Policy, Collateral, Customer 360
agents. This is a thin bridge only — it holds no business logic itself;
`tools-mock` (separate FastAPI service, overview.md §3.1) owns the
deterministic CIC/KYC/AML/valuation/LOS mock data. Kept as two layers so
the service name `tools-mock` stays exactly as named in overview.md while
the agent-facing surface is still MCP-only, per the tool-layer constraint.

Phase 3 adds get_valuation (a thin HTTP call to tools-mock). CIC/KYC/AML
tools are deferred to whenever Customer 360 / Policy's KYC check lands.
"""
# NOTE: deliberately NO `from __future__ import annotations` — see
# mcp-deterministic/app/server.py for why (mcp==1.12.4's FastMCP tool
# registration breaks on PEP 563 stringized annotations for any
# @mcp.tool() function that takes typed parameters).
import os

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

SERVER_NAME = "mcp-external"
PORT = 8202
TOOLS_MOCK_URL = os.environ.get("TOOLS_MOCK_URL", "http://localhost:8100")

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def ping() -> dict:
    """Health-check tool for Phase 0 — replaced by real CIC/KYC/AML/valuation
    tools in Phase 3, each a thin call to tools-mock."""
    return {"status": "ok", "server": SERVER_NAME, "tools_mock_url": TOOLS_MOCK_URL}


@mcp.tool()
def get_valuation(collateral_id: str) -> dict:
    """Fetches the bank's OWN valuation-on-file for a collateral item —
    deliberately a different source (and often a different number) from
    whatever the customer's submitted valuation certificate says. Gives
    Collateral Agent an independent cross-check, not just a rubber stamp
    of the submitted document."""
    resp = httpx.get(f"{TOOLS_MOCK_URL}/valuation/{collateral_id}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def get_credit_obligations(customer_id: str) -> dict:
    """Fetches the customer's EXISTING obligations at the bank (dư nợ +
    dư bảo lãnh + dư L/C — "Tổng nghĩa vụ tại MB", cẩm nang trang 25).
    Collateral & Legal Agent adds the CURRENTLY-requested facility amount
    on top of `total_obligation_vnd` itself (collateral.py) before calling
    calculate_collateral_coverage — this tool only reports what's already
    on the books, not the new request."""
    resp = httpx.get(f"{TOOLS_MOCK_URL}/credit-obligations/{customer_id}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def query_cic_mock(customer_id: str) -> dict:
    """Fetches a mock CIC (Credit Information Center) snapshot — dư nợ tại
    TCTD khác, nhóm nợ theo phân loại NHNN, sự kiện quá hạn, và
    identity_match_score. Guardrail bắt buộc ở caller (worker/app/agents/
    customer360.py): identity_match_score thấp KHÔNG được tự coi là match
    — đây là lý do tồn tại của golden case C05 (ai-architecture.md §5.5)."""
    resp = httpx.get(f"{TOOLS_MOCK_URL}/cic/{customer_id}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def health(_request) -> JSONResponse:
    try:
        resp = httpx.get(f"{TOOLS_MOCK_URL}/health", timeout=5.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"status": "unhealthy", "server": SERVER_NAME, "error": str(exc)},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "server": SERVER_NAME})


# See mcp-deterministic/app/server.py for why the lifespan must be
# re-attached explicitly (streamable_http_app()'s session manager task
# group never starts otherwise — every /mcp POST 500s).
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
