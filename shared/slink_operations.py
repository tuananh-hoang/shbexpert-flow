"""Operations — agent duy nhất HÀNH ĐỘNG, không chỉ đọc và tính.

Năm agent trong engine.py chấm điểm rồi dừng ở khuyến nghị. File này biến
khuyến nghị thành thay đổi thật ngoài hệ thống: cấp, điều chỉnh, treo hạn
mức thấu chi qua core-banking-mock.

Điểm phải cẩn thận nhất của cả lát: KHÔNG được cấp hạn mức hai lần khi job
Redis bị giao lại. Guard nằm ở claim_for_issuing() — xem docstring ở đó.

Spec: docs/superpowers/specs/2026-07-19-slink-operations-design.md
"""
from __future__ import annotations

import datetime as dt
import os

import httpx
from sqlalchemy import update
from sqlalchemy.orm import Session

from shared.models import SlinkApplication, SlinkOverdraftEvent

CORE_BANKING_URL = os.environ.get("CORE_BANKING_URL", "http://core-banking-mock:8500")


class CoreBankingError(RuntimeError):
    """Không thực hiện được thao tác hạn mức.

    Bắt riêng để phân biệt ISSUE_FAILED với REJECTED: engine đã duyệt, chỉ
    là chưa cấp được — một cái là kết luận cuối, một cái cần thử lại.
    """


def _vnd(amount: float | None) -> str:
    return "—" if amount is None else f"{round(amount):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Guard chống cấp hai lần
# ---------------------------------------------------------------------------
def claim_for_scoring(session: Session, application_id: str) -> bool:
    """Giành quyền CHẤM ĐIỂM. True nếu giành được.

    Cùng cơ chế claim_for_issuing nhưng ở đầu job: `UPDATE ... WHERE status
    = 'QUEUED'`. Job bị giao lại sẽ thấy rowcount = 0 và thoát sạch.

    Thiếu guard này thì job giao lại chạy lại engine rồi chết giữa chừng ở
    UniqueViolation của slink_agent_decisions — chống được cấp hai lần,
    nhưng bằng ràng buộc của bảng khác chứ không phải bằng thiết kế, và để
    lại lỗi bẩn trong log. Phát hiện khi chạy kiểm chứng §9 bước 3.
    """
    result = session.execute(
        update(SlinkApplication)
        .where(
            SlinkApplication.slink_application_id == application_id,
            SlinkApplication.status == "QUEUED",
        )
        .values(status="SCORING")
    )
    return result.rowcount == 1


def claim_for_issuing(session: Session, application_id: str) -> bool:
    """Giành quyền cấp hạn mức cho application này. True nếu giành được.

    Guard là phép chuyển trạng thái CÓ ĐIỀU KIỆN trong DB, không phải cờ
    trong bộ nhớ process: `UPDATE ... WHERE status = 'APPROVED'`. Ai thua
    cuộc đua sẽ thấy rowcount = 0 và thoát ngay, KHÔNG gọi core-banking.

    Đây là lý do trạng thái ISSUING tồn tại — nó là chỗ khoá, không phải
    bước trang trí cho UI.
    """
    result = session.execute(
        update(SlinkApplication)
        .where(
            SlinkApplication.slink_application_id == application_id,
            SlinkApplication.status == "APPROVED",
        )
        .values(status="ISSUING")
    )
    return result.rowcount == 1


# ---------------------------------------------------------------------------
# Gọi core-banking
# ---------------------------------------------------------------------------
def _get_current_overdraft(customer_id: str) -> dict | None:
    try:
        response = httpx.get(
            f"{CORE_BANKING_URL}/core-banking/accounts/{customer_id}/overdraft", timeout=10.0
        )
    except httpx.HTTPError as exc:
        raise CoreBankingError(f"không gọi được core-banking: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise CoreBankingError(f"core-banking trả {response.status_code}")
    return response.json()


def issue_overdraft(customer_id: str, limit_vnd: int, rate_pct: float, reason: str) -> dict:
    try:
        response = httpx.post(
            f"{CORE_BANKING_URL}/core-banking/accounts/{customer_id}/overdraft",
            json={"limit_vnd": limit_vnd, "interest_rate_pct": rate_pct, "reason": reason},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise CoreBankingError(f"không gọi được core-banking: {exc}") from exc
    if response.status_code not in (200, 201):
        raise CoreBankingError(f"core-banking từ chối cấp hạn mức: {response.status_code} {response.text}")
    return response.json()


def adjust_limit(customer_id: str, new_limit_vnd: int, reason: str) -> dict:
    try:
        response = httpx.patch(
            f"{CORE_BANKING_URL}/core-banking/accounts/{customer_id}/overdraft-limit",
            json={"new_limit_vnd": new_limit_vnd, "reason": reason},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise CoreBankingError(f"không gọi được core-banking: {exc}") from exc
    if response.status_code != 200:
        raise CoreBankingError(f"core-banking từ chối điều chỉnh: {response.status_code}")
    return response.json()


def suspend_overdraft(customer_id: str, reason: str) -> dict:
    try:
        response = httpx.post(
            f"{CORE_BANKING_URL}/core-banking/accounts/{customer_id}/overdraft/suspend",
            json={"reason": reason},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise CoreBankingError(f"không gọi được core-banking: {exc}") from exc
    if response.status_code != 200:
        raise CoreBankingError(f"core-banking từ chối treo hạn mức: {response.status_code}")
    return response.json()


# ---------------------------------------------------------------------------
# Ghi sổ
# ---------------------------------------------------------------------------
def record_event(
    session: Session,
    *,
    customer_id: str,
    application_id: str | None,
    action: str,
    limit_before: int | None,
    limit_after: int | None,
    rate_pct: float | None,
    reason: str,
    succeeded: bool,
    response: dict,
) -> None:
    session.add(
        SlinkOverdraftEvent(
            customer_id=customer_id,
            slink_application_id=application_id,
            action=action,
            limit_before_vnd=limit_before,
            limit_after_vnd=limit_after,
            interest_rate_pct=rate_pct,
            reason=reason,
            succeeded=succeeded,
            core_banking_response=response,
        )
    )


def mark_issued(session: Session, application_id: str) -> None:
    app_row = session.get(SlinkApplication, application_id)
    app_row.status = "ISSUED"
    app_row.decided_at = dt.datetime.now(dt.timezone.utc)


def mark_issue_failed(session: Session, application_id: str, reason: str) -> None:
    app_row = session.get(SlinkApplication, application_id)
    # KHÔNG phải REJECTED: engine đã duyệt, chỉ là chưa cấp được.
    app_row.status = "ISSUE_FAILED"
    app_row.decision_reason = f"{app_row.decision_reason or ''} | cấp hạn mức thất bại: {reason}".strip(" |")
    app_row.decided_at = dt.datetime.now(dt.timezone.utc)


def operations_summary(limit_vnd: int, rate_pct: float) -> str:
    return f"Đã cấp hạn mức thấu chi {_vnd(limit_vnd)} VND, lãi suất {rate_pct:.1f}%/năm."


def current_limit(customer_id: str) -> int | None:
    """Hạn mức ĐANG DÙNG ĐƯỢC theo core-banking, None nếu không có.

    Đọc từ core-banking chứ không từ DB của ta: nó là nguồn sự thật của
    hạn mức (spec §2), DB ta chỉ ghi lại đã yêu cầu gì và nhận về gì.

    Tài khoản đã treo trả None chứ KHÔNG trả limit_vnd còn lưu: core-banking
    giữ nguyên con số đó khi suspend (chỉ hạ available_vnd về 0), nên trả
    thẳng nó ra sẽ khiến một tài khoản bị treo trông như vẫn còn hạn mức —
    và đường sốc dòng tiền sẽ đi điều chỉnh một tài khoản đã treo. Phát
    hiện khi chạy kiểm chứng end-to-end §9 bước 7.
    """
    record = _get_current_overdraft(customer_id)
    if record is None or record["status"] == "suspended":
        return None
    return record["limit_vnd"]


def current_overdraft_status(customer_id: str) -> str | None:
    """Trạng thái thô: active | reduced | suspended, None nếu chưa có."""
    record = _get_current_overdraft(customer_id)
    return None if record is None else record["status"]
