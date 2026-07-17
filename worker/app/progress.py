"""Publishes per-step progress events to the case's Redis pub/sub channel
— the "thinking" trace the Analyzing screen shows (frontend-flow plan
Phase 2). Distinct from worker/app/main.py's `_publish` (which only
emits the coarse job_started/job_completed/job_failed) — this is called
from INSIDE the LangGraph graph itself (build.py), once per real node
start/end, so the frontend shows the actual execution order (including
the 3 expert agents' genuine parallelism) instead of a guessed timeline.

Opens a short-lived connection per call rather than a shared one, same
pattern as the sync DB helpers in agents/common.py — a node already runs
via asyncio, so this stays a tiny async helper rather than needing a
process-wide client.
"""
from __future__ import annotations

import json

import redis.asyncio as aioredis

from app.config import REDIS_URL, progress_channel


async def publish_progress(case_id: str, event: dict) -> None:
    r = aioredis.from_url(REDIS_URL)
    try:
        await r.publish(progress_channel(case_id), json.dumps(event))
    finally:
        await r.aclose()
