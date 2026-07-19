"""Phân luồng xanh/đỏ khi tiếp nhận hồ sơ — cửa vào chung của cả hai kênh.

Spec: docs/superpowers/specs/2026-07-19-intake-routing-design.md

Tách khỏi intake.py: file đó lo vòng đời tài liệu của MỘT case đã tồn tại,
còn file này quyết định hồ sơ vừa tới có sinh ra case hay không. Hai mối
quan tâm khác nhau, và routing nằm phía trên cả `cases` lẫn domain SLINK.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

import json
import os

import redis.asyncio as aioredis

from shared.constants import VALID_CHANNELS, VALID_PRODUCTS, VALID_SEGMENTS
from shared.db import get_session
from shared.models import RoutingDecision, SlinkApplication
from shared.queue import SLINK_SCORING_QUEUE
from shared.routing import GREEN, RED, classify_lane

from ..slink_client import SlinkUnavailableError, merchant_exists
from .intake import create_case_row

router = APIRouter(prefix="/intake", tags=["routing"])

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RequestedFacility(BaseModel):
    amount_vnd: int = Field(gt=0)
    tenor_months: int = Field(gt=0)


class SubmissionRequest(BaseModel):
    channel: str
    customer_id: str = Field(min_length=1)
    segment: str
    product: str
    requested_facility: RequestedFacility
    owner: str = Field(min_length=1)

    @field_validator("channel")
    @classmethod
    def _check_channel(cls, v: str) -> str:
        if v not in VALID_CHANNELS:
            raise ValueError(f"channel không hợp lệ: {v!r} (hợp lệ: {sorted(VALID_CHANNELS)})")
        return v

    @field_validator("segment")
    @classmethod
    def _check_segment(cls, v: str) -> str:
        if v not in VALID_SEGMENTS:
            raise ValueError(f"segment không hợp lệ: {v!r} (hợp lệ: {sorted(VALID_SEGMENTS)})")
        return v

    @field_validator("product")
    @classmethod
    def _check_product(cls, v: str) -> str:
        if v not in VALID_PRODUCTS:
            raise ValueError(f"product không hợp lệ: {v!r} (hợp lệ: {sorted(VALID_PRODUCTS)})")
        return v


def _decision_dict(d: RoutingDecision) -> dict:
    return {
        "routing_decision_id": d.routing_decision_id,
        "channel": d.channel,
        "lane": d.lane,
        "customer_id": d.customer_id,
        "segment": d.segment,
        "product": d.product,
        "amount_vnd": d.amount_vnd,
        "tenor_months": d.tenor_months,
        "reason": d.reason,
        "case_id": d.case_id,
        "decided_at": d.decided_at.isoformat(),
    }


@router.post("/submissions", status_code=201)
async def create_submission(body: SubmissionRequest) -> dict:
    """Tiếp nhận một hồ sơ và phân luồng ngay.

    Ba kết cục (spec 2026-07-19-slink-scoring-design.md §3):

    (a) Luật không đạt          -> RED, tạo Case, đồng bộ
    (b) Luật đạt nhưng 404      -> RED, tạo Case, reason ghi rõ lý do hạ luồng
    (c) Luật đạt và có merchant -> GREEN, tạo SlinkApplication, xếp hàng chấm điểm

    `classify_lane` là hàm THUẦN và phải giữ nguyên như vậy — việc kiểm
    merchant có tồn tại không được nhét vào nó, mà compose ở đây. Nhờ vậy
    hàm luật và test của nó không đổi một dòng nào khi lát (b) thêm nhánh.

    Kiểm ở đây chứ không hoãn xuống worker: hoãn thì đã lỡ trả GREEN, đã
    tạo thực thể SLINK, đã mở SSE, rồi mới phải lật ngược sang đỏ và tạo
    case muộn. Chốt luồng trước khi cam kết nó.
    """
    result = classify_lane(
        product=body.product,
        segment=body.segment,
        amount_vnd=body.requested_facility.amount_vnd,
    )

    lane = result.lane
    reason = result.reason

    if lane == GREEN:
        try:
            has_merchant = merchant_exists(body.customer_id)
        except SlinkUnavailableError as exc:
            # 502 chứ không âm thầm hạ luồng đỏ — xem SlinkUnavailableError.
            raise HTTPException(502, str(exc)) from exc

        if not has_merchant:
            # Luồng CUỐI thắng: ghi RED, không phải GREEN kèm cờ phụ. Nếu
            # ghi GREEN thì engine luồng xanh sẽ xử lý một hồ sơ đáng lẽ
            # thuộc về người.
            lane = RED
            reason = f"{result.reason} — nhưng chưa có lịch sử giao dịch SLINK, chuyển luồng đỏ"

    with get_session() as session:
        case_id: str | None = None
        slink_application_id: str | None = None

        if lane == RED:
            case = create_case_row(
                session,
                customer_id=body.customer_id,
                product=body.product,
                requested_facility=body.requested_facility.model_dump(),
                owner=body.owner,
            )
            case_id = case.case_id

        decision = RoutingDecision(
            channel=body.channel,
            lane=lane,
            customer_id=body.customer_id,
            segment=body.segment,
            product=body.product,
            amount_vnd=body.requested_facility.amount_vnd,
            tenor_months=body.requested_facility.tenor_months,
            reason=reason,
            case_id=case_id,
        )
        session.add(decision)
        session.flush()

        if lane == GREEN:
            application = SlinkApplication(
                routing_decision_id=decision.routing_decision_id,
                customer_id=body.customer_id,
                amount_requested_vnd=body.requested_facility.amount_vnd,
                tenor_months=body.requested_facility.tenor_months,
                status="QUEUED",
            )
            session.add(application)
            session.flush()
            slink_application_id = application.slink_application_id
            decision.slink_application_id = slink_application_id

        response = {
            "routing_decision_id": decision.routing_decision_id,
            "lane": lane,
            "reason": reason,
            "case_id": case_id,
            "slink_application_id": slink_application_id,
        }

    # Đẩy job SAU khi transaction đã commit (ra khỏi khối `with`): worker
    # đọc application từ DB ngay khi nhận job, nên hàng đợi không được biết
    # tới nó trước khi nó tồn tại.
    if slink_application_id is not None:
        r = aioredis.from_url(REDIS_URL)
        try:
            await r.lpush(
                SLINK_SCORING_QUEUE,
                json.dumps({"slink_application_id": slink_application_id}),
            )
        finally:
            await r.aclose()
        response["status"] = "QUEUED"

    return response


@router.get("/routing-decisions/{routing_decision_id}")
def get_routing_decision(routing_decision_id: str) -> dict:
    with get_session() as session:
        decision = session.get(RoutingDecision, routing_decision_id)
        if decision is None:
            raise HTTPException(404, f"routing decision {routing_decision_id!r} không tồn tại")
        return _decision_dict(decision)
