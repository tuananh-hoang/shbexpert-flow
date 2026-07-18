"""FastAPI entrypoint for the `api` service.

api is the ONLY writer of CaseState (overview.md §4: "web không gọi thẳng
postgres/qdrant/minio/tools-mock — mọi thứ qua api"). This file currently
only exposes a health check; REST + SSE endpoints for cases/findings/
decisions are added in later phases (Phase 1 state layer, Phase 2 analyze
endpoint).
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
import redis

from shared.db import ping as db_ping

from app.routers import cases, chat, internal, memo

app = FastAPI(title="SHBExpert Flow API")
app.include_router(cases.router)
app.include_router(chat.router)
app.include_router(memo.router)
app.include_router(internal.router)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@app.get("/health")
def health() -> dict:
    """Checks Postgres and Redis connectivity. MinIO check added once the
    document-seeding path (Phase 1) exercises it."""
    problems: list[str] = []

    try:
        db_ping()
    except Exception as exc:  # noqa: BLE001 - surface any DB error to caller
        problems.append(f"postgres: {exc}")

    try:
        redis.from_url(REDIS_URL).ping()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"redis: {exc}")

    if problems:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "problems": problems})

    return {"status": "ok"}
