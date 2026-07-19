"""Dynamic Risk Control — dòng tiền sụt thì siết hạn mức đang hoạt động.

Khác đường cấp mới ở một điểm quan trọng: đây là ĐIỀU CHỈNH hạn mức đã có,
KHÔNG tạo SlinkApplication mới. Nhét vào cùng bảng đề nghị sẽ làm "số đề
nghị" trong báo cáo sai — một merchant bị siết hạn mức ba lần sẽ trông như
đã nộp bốn đề nghị.

Spec: docs/superpowers/specs/2026-07-19-slink-operations-design.md §7
"""
from __future__ import annotations

import os

import httpx

from shared.db import get_session

from shared.slink_engine import (
    run_behavioural_agent,
    run_cashflow_agent,
    run_risk_compliance_agent,
    run_sizing_pricing_agent,
)
from shared.slink_operations import (
    CoreBankingError,
    adjust_limit,
    current_limit,
    record_event,
    suspend_overdraft,
)

SLINK_MOCK_URL = os.environ.get("SLINK_MOCK_URL", "http://slink-mock:8400")


def apply_cashflow_shock(customer_id: str, shock_pct: float) -> dict:
    """Chấm lại merchant dưới cú sốc và siết hạn mức nếu cần.

    Trả về mô tả việc đã làm. Ba kết cục:
      - risk chặn            -> treo hạn mức (SUSPEND)
      - hạn mức mới thấp hơn -> giảm (ADJUST)
      - không xấu đi         -> không làm gì, không ghi event
    """
    response = httpx.get(
        f"{SLINK_MOCK_URL}/slink/merchants/{customer_id}",
        params={"shock_pct": shock_pct},
        timeout=10.0,
    )
    if response.status_code == 404:
        raise CoreBankingError(f"khách hàng {customer_id!r} chưa có lịch sử SLINK")
    response.raise_for_status()
    merchant = response.json()

    existing_limit = current_limit(customer_id)
    if existing_limit is None:
        raise CoreBankingError(f"khách hàng {customer_id!r} chưa có hạn mức thấu chi để điều chỉnh")

    cashflow = run_cashflow_agent(merchant)
    behavioural = run_behavioural_agent(merchant)
    risk = run_risk_compliance_agent(
        merchant,
        silent_days=cashflow.metrics["silent_days"],
        mom_growth_pct=cashflow.metrics["mom_growth_pct"],
    )

    # --- risk chặn -> treo hẳn ---------------------------------------------
    if risk.metrics["blocked"]:
        cb_response = suspend_overdraft(customer_id, reason=risk.summary)
        with get_session() as session:
            record_event(
                session,
                customer_id=customer_id,
                application_id=None,
                action="SUSPEND",
                limit_before=existing_limit,
                limit_after=0,
                rate_pct=None,
                reason=risk.summary,
                succeeded=True,
                response=cb_response,
            )
        return {
            "action": "SUSPEND",
            "limit_before_vnd": existing_limit,
            "limit_after_vnd": 0,
            "reason": risk.summary,
            "cashflow": cashflow.metrics,
        }

    # --- không chặn -> tính lại hạn mức -------------------------------------
    sizing = run_sizing_pricing_agent(
        merchant,
        avg_monthly_revenue_vnd=cashflow.metrics["avg_monthly_revenue_vnd"],
        behavioural_score=behavioural.metrics["behavioural_score"],
        volatility_pct=cashflow.metrics["volatility_pct"],
    )
    new_limit = sizing.metrics["recommended_limit_vnd"]

    if new_limit >= existing_limit:
        # Chỉ siết, không tự nới: nới hạn mức là quyết định khác, cần
        # đường đi riêng chứ không phải hệ quả phụ của một cú sốc.
        return {
            "action": "NONE",
            "limit_before_vnd": existing_limit,
            "limit_after_vnd": existing_limit,
            "reason": f"Hạn mức tính lại ({new_limit}) không thấp hơn hiện tại — giữ nguyên.",
            "cashflow": cashflow.metrics,
        }

    cb_response = adjust_limit(customer_id, new_limit, reason=f"sốc dòng tiền -{shock_pct:.0f}%")
    with get_session() as session:
        record_event(
            session,
            customer_id=customer_id,
            application_id=None,
            action="ADJUST",
            limit_before=existing_limit,
            limit_after=new_limit,
            rate_pct=sizing.metrics["interest_rate_pct"],
            reason=f"sốc dòng tiền -{shock_pct:.0f}%: {sizing.summary}",
            succeeded=True,
            response=cb_response,
        )

    return {
        "action": "ADJUST",
        "limit_before_vnd": existing_limit,
        "limit_after_vnd": new_limit,
        "reason": f"Dòng tiền giảm {shock_pct:.0f}% — siết hạn mức.",
        "cashflow": cashflow.metrics,
    }
