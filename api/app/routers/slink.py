"""Đọc kết quả chấm điểm luồng xanh.

Tách khỏi routing.py: file đó lo ngã ba tiếp nhận, file này lo vòng đời
một SlinkApplication đã được tạo.

Không có endpoint danh sách gộp với `GET /cases` — luồng xanh không hiện
trong hàng đợi Credit Officer, đúng tinh thần "không qua Credit Officer"
(spec 2026-07-19-intake-routing-design.md §2.1).
"""
from __future__ import annotations

import asyncio
import json
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel, Field

from shared.db import get_session
from shared.models import SlinkAgentDecision, SlinkApplication, SlinkOverdraftEvent
from shared.queue import slink_progress_channel
from shared.slink_operations import CoreBankingError, current_limit, current_overdraft_status
from shared.slink_shock import apply_cashflow_shock

router = APIRouter(prefix="/slink", tags=["slink"])

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@router.get("/applications/{slink_application_id}")
def get_application(slink_application_id: str) -> dict:
    with get_session() as session:
        app_row = session.get(SlinkApplication, slink_application_id)
        if app_row is None:
            raise HTTPException(404, f"đề nghị {slink_application_id!r} không tồn tại")

        decisions = (
            session.execute(
                select(SlinkAgentDecision)
                .where(SlinkAgentDecision.slink_application_id == slink_application_id)
                .order_by(SlinkAgentDecision.seq)
            )
            .scalars()
            .all()
        )

        return {
            "slink_application_id": app_row.slink_application_id,
            "customer_id": app_row.customer_id,
            "amount_requested_vnd": app_row.amount_requested_vnd,
            "tenor_months": app_row.tenor_months,
            "status": app_row.status,
            "recommended_limit_vnd": app_row.recommended_limit_vnd,
            "interest_rate_pct": app_row.interest_rate_pct,
            "decision_reason": app_row.decision_reason,
            "created_at": app_row.created_at.isoformat(),
            "decided_at": app_row.decided_at.isoformat() if app_row.decided_at else None,
            "agent_decisions": [
                {
                    "agent_id": d.agent_id,
                    "summary": d.summary,
                    "rationale": d.rationale,
                    "metrics": d.metrics,
                    "seq": d.seq,
                }
                for d in decisions
            ],
        }


@router.get("/applications/{slink_application_id}/stream")
async def stream_progress(slink_application_id: str) -> EventSourceResponse:
    """SSE tiến trình chấm điểm.

    Kênh khoá theo slink_application_id chứ KHÔNG theo case_id — luồng xanh
    không sinh ra case nào.
    """
    with get_session() as session:
        if session.get(SlinkApplication, slink_application_id) is None:
            raise HTTPException(404, f"đề nghị {slink_application_id!r} không tồn tại")

    async def event_source():
        r = aioredis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(slink_progress_channel(slink_application_id))
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                if message is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                payload = message["data"]
                yield {"event": "progress", "data": payload.decode() if isinstance(payload, bytes) else payload}
                try:
                    if json.loads(payload)["phase"] in {"APPROVED", "REJECTED", "FAILED"}:
                        break
                except (ValueError, KeyError):
                    pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await r.aclose()

    return EventSourceResponse(event_source())


class ShockRequest(BaseModel):
    shock_pct: float = Field(gt=0, le=95, description="phần trăm sụt dòng tiền 30 ngày gần nhất")


@router.post("/customers/{customer_id}/shock")
def trigger_cashflow_shock(customer_id: str, body: ShockRequest) -> dict:
    """Dynamic Risk Control — mô phỏng cú sốc dòng tiền rồi siết hạn mức.

    Chạy đồng bộ chứ không qua hàng đợi: engine tất định chạy vài trăm ms,
    và bên gọi cần biết ngay hạn mức đã đổi thành bao nhiêu.

    KHÔNG tạo SlinkApplication mới — đây là điều chỉnh hạn mức đang có.
    Nhét vào bảng đề nghị sẽ làm "số đề nghị" trong báo cáo sai: một
    merchant bị siết ba lần sẽ trông như đã nộp bốn đề nghị.
    """
    try:
        return apply_cashflow_shock(customer_id, body.shock_pct)
    except CoreBankingError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"không thực hiện được điều chỉnh: {exc}") from exc


@router.get("/customers/{customer_id}/overdraft")
def get_customer_overdraft(customer_id: str) -> dict:
    """Hạn mức hiện tại + lịch sử mọi lần chạm vào nó.

    `current_limit_vnd` đọc từ core-banking (nguồn sự thật), `events` đọc
    từ DB ta. Trả cả hai để thấy được khi hai bên lệch nhau — mock giữ
    trạng thái trong bộ nhớ nên restart là mất, và khi đó DB vẫn còn lịch
    sử trong khi core-banking đã quên.
    """
    try:
        limit = current_limit(customer_id)
        status = current_overdraft_status(customer_id)
    except CoreBankingError as exc:
        raise HTTPException(502, str(exc)) from exc

    with get_session() as session:
        events = (
            session.execute(
                select(SlinkOverdraftEvent)
                .where(SlinkOverdraftEvent.customer_id == customer_id)
                .order_by(SlinkOverdraftEvent.created_at)
            )
            .scalars()
            .all()
        )
        return {
            "customer_id": customer_id,
            # None khi tài khoản đã treo — xem current_limit().
            "current_limit_vnd": limit,
            "overdraft_status": status,
            "events": [
                {
                    "action": e.action,
                    "limit_before_vnd": e.limit_before_vnd,
                    "limit_after_vnd": e.limit_after_vnd,
                    "reason": e.reason,
                    "succeeded": e.succeeded,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }
