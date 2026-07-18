"""Chat endpoints — ai-architecture_v2.md §11.8 MVP Chat.

`api` owns the write path for the Credit Officer's own message (a plain
DB write, no LLM involved — same "api is the only writer of CaseState"
rule as everything else) and RELAYS the assistant's streamed response from
`worker`'s Chat Orchestrator (`worker` remains the only process that
touches an LLM SDK — worker/app/llm/adapter.py). `api` does not persist
the assistant's message itself; `worker` does that after its own stream
finishes (worker/app/chat/server.py) — this endpoint's job is purely to
write the user's turn and pipe bytes through.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from starlette.responses import StreamingResponse

from shared.db import get_session
from shared.models import Case, ChatMessage
from shared.state import get_or_create_chat_thread, write_chat_message

router = APIRouter(prefix="/cases", tags=["chat"])

WORKER_INTERNAL_URL = os.environ.get("WORKER_INTERNAL_URL", "http://worker:8300")


class ChatMessageRequest(BaseModel):
    content: str


def _message_dict(m: ChatMessage) -> dict:
    return {
        "message_id": m.message_id,
        "seq": m.seq,
        "role": m.role,
        "content": m.content,
        "citations": m.citations,
        "created_at": m.created_at.isoformat(),
    }


@router.get("/{case_id}/chat/messages")
def list_chat_messages(case_id: str) -> dict:
    with get_session() as session:
        if session.get(Case, case_id) is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")
        thread = get_or_create_chat_thread(session, case_id)
        rows = (
            session.execute(select(ChatMessage).where(ChatMessage.thread_id == thread.thread_id).order_by(ChatMessage.seq))
            .scalars()
            .all()
        )
        return {"thread_id": thread.thread_id, "messages": [_message_dict(m) for m in rows]}


@router.post("/{case_id}/chat/messages")
async def send_chat_message(case_id: str, body: ChatMessageRequest) -> StreamingResponse:
    with get_session() as session:
        if session.get(Case, case_id) is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")
        thread = get_or_create_chat_thread(session, case_id)
        write_chat_message(session, thread_id=thread.thread_id, role="USER", content=body.content)
        thread_id = thread.thread_id

    async def relay():
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream(
                "POST",
                f"{WORKER_INTERNAL_URL}/chat/turn",
                json={"case_id": case_id, "thread_id": thread_id, "content": body.content},
            ) as upstream:
                async for chunk in upstream.aiter_text():
                    yield chunk

    return StreamingResponse(relay(), media_type="text/plain; charset=utf-8")
