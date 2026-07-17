"""Entrypoint for the `worker` service (LangGraph runtime).

Consumes analyze jobs enqueued by `api` (Redis list ANALYZE_QUEUE), runs
the LangGraph graph per case (worker/app/graph/build.py), and publishes
progress to a per-case Redis pub/sub channel that `api`'s SSE endpoint
forwards to the browser (overview.md §4: worker -> redis -> api -> SSE).

Note on sync-inside-async: shared/db.py's Session and shared/state.py's
write_finding() are synchronous SQLAlchemy calls, invoked here from inside
async agent code. That's a deliberate simplification for this scope (one
case processed at a time, not high-concurrency) — it briefly blocks the
event loop per DB call rather than requiring a second async SQLAlchemy
engine. Revisit if Phase 3's parallel FanOut needs true concurrent DB
access from multiple agents at once.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import redis.asyncio as aioredis

from shared.db import ping as db_ping
from app.config import ANALYZE_QUEUE, REDIS_URL, progress_channel
from app.graph.build import Checkpointer, build_compiled_graph

HEARTBEAT_PATH = "/tmp/heartbeat"


async def wait_for_dependencies(max_attempts: int = 30, delay_seconds: float = 2.0) -> None:
    r = aioredis.from_url(REDIS_URL)
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                db_ping()
                await r.ping()
                print(f"[worker] dependencies ready after {attempt} attempt(s)", flush=True)
                return
            except Exception as exc:  # noqa: BLE001
                print(f"[worker] waiting for dependencies (attempt {attempt}): {exc}", flush=True)
                await asyncio.sleep(delay_seconds)
    finally:
        await r.aclose()
    print("[worker] dependencies never became ready — exiting", flush=True)
    sys.exit(1)


async def _heartbeat_loop() -> None:
    while True:
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(str(time.time()))
        await asyncio.sleep(15)


async def _publish(r: aioredis.Redis, case_id: str, event: dict) -> None:
    await r.publish(progress_channel(case_id), json.dumps(event))


async def _consume_jobs(compiled_graph) -> None:
    r = aioredis.from_url(REDIS_URL)
    print(f"[worker] listening on redis list {ANALYZE_QUEUE!r}", flush=True)
    while True:
        item = await r.brpop(ANALYZE_QUEUE, timeout=5)
        if item is None:
            continue  # timeout — loop back so the heartbeat/cancellation stay responsive
        _key, raw = item
        job = json.loads(raw)
        case_id = job["case_id"]
        print(f"[worker] dequeued analyze job for case {case_id}", flush=True)
        await _publish(r, case_id, {"type": "job_started", "case_id": case_id})
        try:
            result = await compiled_graph.ainvoke(
                {"case_id": case_id, "findings_written": []},
                config={"configurable": {"thread_id": case_id}},
            )
            await _publish(
                r,
                case_id,
                {"type": "job_completed", "case_id": case_id, "findings_written": result["findings_written"]},
            )
            print(f"[worker] case {case_id} done: {result['findings_written']}", flush=True)
        except Exception as exc:  # noqa: BLE001 — a bad job must not kill the consumer loop
            print(f"[worker] job for case {case_id} failed: {exc}", flush=True)
            await _publish(r, case_id, {"type": "job_failed", "case_id": case_id, "error": str(exc)})


async def main() -> None:
    await wait_for_dependencies()
    asyncio.create_task(_heartbeat_loop())

    async with Checkpointer() as saver:
        compiled_graph = await build_compiled_graph(saver)
        print("[worker] ready — graph compiled, checkpointer connected", flush=True)
        await _consume_jobs(compiled_graph)


if __name__ == "__main__":
    asyncio.run(main())
