"""Shared helpers for expert agents — reading already-"OCR'd" data, and the
async/sync bridge that avoids a real deadlock found while testing Phase 3's
FanOut (see the long comment on `run_sync` below).

Per the user's constraint, no agent here ever touches OCR/extraction
logic; they only read ExtractedField rows a seed script (or, in a real
system, the Document Processing Pipeline) already wrote.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, TypeVar

from sqlalchemy import select

from shared.db import get_session
from shared.models import Case, Document, ExtractedField
from shared.schemas import Actor, FindingIn, FindingOut
from shared.state import write_finding

T = TypeVar("T")


async def run_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Runs a blocking (sync SQLAlchemy) call in a worker thread instead of
    directly on the asyncio event loop.

    Why this exists — a real deadlock, reproduced and diagnosed live during
    Phase 3 testing, not a theoretical concern:

    LangGraph's FanOut runs Financial/Policy/Collateral as concurrent
    coroutines on ONE event loop thread. Each agent opens a sync SQLAlchemy
    session, does a blocking read, then `await`s async I/O (an MCP tool
    call, an LLM completion) WHILE the transaction stays open, then later
    does a blocking write (`write_finding`, which takes a per-case Postgres
    advisory lock via `pg_advisory_xact_lock`). Financial writes TWO
    findings in the same session/transaction, so it holds that advisory
    lock from its first write clear through a second round of awaits.

    Sequence that deadlocked: Financial's session grabs the 'C06' advisory
    lock during its first write_finding, then awaits `calculate_coverage`
    for its second finding — control returns to the event loop, which runs
    Collateral's coroutine. Collateral's own write_finding tries to grab
    the SAME advisory lock and BLOCKS — but that block is a *synchronous*
    psycopg2 call, so it freezes the entire single-threaded event loop.
    Financial's pending async HTTP response (for `calculate_coverage`) can
    now never be processed, so Financial's session never commits, so the
    lock it holds is never released, so Collateral's blocking call waits
    forever. Confirmed via `pg_stat_activity`: two sessions "idle in
    transaction" holding locks mid-await, one session `active` stuck on
    `pg_advisory_xact_lock`, worker CPU at 0% (genuinely blocked, not busy).

    Fix: every DB read/write is now a short, self-contained sync function
    (opens a session, does ONE thing, commits, closes) executed via
    `asyncio.to_thread`. A blocking call now blocks its OWN OS thread, not
    the event loop — so other coroutines' pending async I/O keeps
    progressing, sessions commit promptly, and advisory locks are never
    held across an await boundary.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------------------
# Sync helpers — each opens and closes its OWN session. Call these only via
# run_sync() from agent code, never directly from an async function body.
# ---------------------------------------------------------------------------
def read_extracted_fields_sync(case_id: str) -> dict[str, dict]:
    """Returns {field_key: {"value": ..., "evidence_id": field_id}} for
    every ExtractedField belonging to any Document of this case."""
    with get_session() as session:
        rows = session.execute(
            select(ExtractedField, Document.document_id)
            .join(Document, ExtractedField.document_id == Document.document_id)
            .where(Document.case_id == case_id)
        ).all()
        return {
            row.ExtractedField.field_key: {
                "value": row.ExtractedField.value,
                "evidence_id": row.ExtractedField.field_id,
            }
            for row in rows
        }


def read_requested_facility_sync(case_id: str) -> dict:
    """Returns Case.requested_facility as a plain dict — deliberately NOT
    the ORM object, so nothing outside this function ever touches an
    instance whose session has already closed."""
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id!r} not found")
        return dict(case.requested_facility)


def write_finding_sync(
    finding: FindingIn,
    *,
    finding_key: str | None = None,
    versions: dict[str, str] | None = None,
) -> FindingOut:
    with get_session() as session:
        return write_finding(session, finding, finding_key=finding_key, versions=versions)


def emit_event_sync(case_id: str, event_type: str, actor: Actor, payload: dict | None = None) -> None:
    from shared.state import emit_event

    with get_session() as session:
        emit_event(session, case_id=case_id, event_type=event_type, actor=actor, payload=payload or {})


def unwrap_mcp_result(result):
    """FastMCP tools return a LIST of content blocks over the wire
    (`[{"type": "text", "text": "<json string>", "id": "..."}]`), not a
    pre-parsed dict — verified empirically in Phase 2/3 smoke tests. Some
    future langchain-mcp-adapters version might start auto-parsing
    structured content, so a bare dict is handled too."""
    if isinstance(result, dict):
        return result
    return json.loads(result[0]["text"])
