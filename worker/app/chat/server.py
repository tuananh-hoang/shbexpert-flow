"""Chat Orchestrator's internal HTTP surface — ai-architecture_v2.md
§11.8. Runs INSIDE the `worker` process (asyncio task alongside the
analyze-job consumer loop, worker/app/main.py) — worker gets its first
ever HTTP port here, reachable only from the `internal` Docker network
(no Caddy route, no host port publish; same posture as the mcp-*
servers). Only `api` calls this (api/app/routers/chat.py).

Deliberately NOT FastAPI/uvicorn's higher-level app factory — a plain
Starlette app, same minimal pattern as mcp-*/app/server.py, since this
process needs no OpenAPI docs or dependency injection, just one route.
"""
from __future__ import annotations

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from app.agents.common import run_sync
from app.chat.orchestrator import handle_chat_turn
from shared.db import get_session
from shared.schemas import Actor
from shared.state import emit_event, write_chat_message

PORT = 8300


def _write_assistant_message_sync(case_id: str, thread_id: str, content: str) -> None:
    with get_session() as session:
        message = write_chat_message(session, thread_id=thread_id, role="ASSISTANT", content=content)
        # Same audit discipline as every other write in this system
        # (shared/state.py::write_finding/write_decision) — a chat reply
        # is an AGENT action, not a side-effect-free read, so it gets an
        # Event row too.
        emit_event(
            session,
            case_id=case_id,
            event_type="CHAT_MESSAGE",
            actor=Actor(type="AGENT", id="chat_orchestrator"),
            payload={"thread_id": thread_id, "message_id": message.message_id},
        )


async def chat_turn(request: Request) -> StreamingResponse:
    body = await request.json()
    case_id = body["case_id"]
    thread_id = body["thread_id"]
    message = body["content"]

    async def generate():
        chunks: list[str] = []
        async for chunk in handle_chat_turn(case_id, thread_id, message):
            chunks.append(chunk)
            yield chunk
        # Persisted AFTER the full stream is sent — the ASSISTANT message
        # is written once, whole, never partial (shared/state.py::
        # write_chat_message is append-only, same discipline as Finding
        # writes: no "streaming into the DB row" half-state).
        full_text = "".join(chunks)
        await run_sync(_write_assistant_message_sync, case_id, thread_id, full_text)

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "worker-chat"})


app = Starlette(routes=[Route("/health", health), Route("/chat/turn", chat_turn, methods=["POST"])])


async def serve() -> None:
    """Called from worker/app/main.py as a background asyncio task,
    running concurrently with the analyze-job consumer loop in the same
    process — not a separate container."""
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
