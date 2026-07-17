"""mcp-state — MCP server for the ONLY tools with real side effects.

Allowlist (ai-architecture.md §6.1): Orchestrator ONLY. Expert agents never
connect to this server — this is what makes "chỉ Orchestrator được gọi tool
có side effect" (overview.md §4) a fact about network topology, not a
convention. Tools here (create_info_request, update_case_status,
create_condition_tasks, generate_credit_memo) do NOT write to Postgres
themselves — they call internal endpoints on `api`, which owns the state
layer and enforces the 4 mandatory things for any state-changing tool
(overview.md §6 nguyên tắc 2): RBAC, schema validation, idempotency key,
audit event.

Phase 5 adds update_case_status (a thin HTTP call to api's /internal
transition endpoint — the ONLY thing this tool does; RBAC/idempotency/
audit all live in api, not here). create_info_request and
create_condition_tasks are deferred to whichever later phase needs them.
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

SERVER_NAME = "mcp-state"
PORT = 8203
API_INTERNAL_URL = os.environ.get("API_INTERNAL_URL", "http://localhost:8000")

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def ping() -> dict:
    """Health-check tool for Phase 0 — replaced by real side-effect tools
    (create_info_request, update_case_status, create_condition_tasks,
    generate_credit_memo) starting Phase 4."""
    return {"status": "ok", "server": SERVER_NAME, "api_internal_url": API_INTERNAL_URL}


@mcp.tool()
def update_case_status(case_id: str, new_state: str, reason: str) -> dict:
    """Transitions a case's state machine position (data-flow.md §2). This
    tool has NO logic of its own beyond the HTTP call — validity checking,
    audit event emission, and the append-only guarantee all live in api's
    state layer (shared.state.transition_state), reached over the network,
    never imported directly. That's the point: even a bug in this file
    can't bypass those checks, because this file doesn't have the
    capability to write to Postgres at all."""
    resp = httpx.post(
        f"{API_INTERNAL_URL}/internal/cases/{case_id}/transition",
        json={"new_state": new_state, "reason": reason, "actor_type": "AGENT", "actor_id": "orchestrator"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


async def health(_request) -> JSONResponse:
    try:
        resp = httpx.get(f"{API_INTERNAL_URL}/health", timeout=5.0)
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
