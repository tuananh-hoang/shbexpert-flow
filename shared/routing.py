"""Luật phân luồng xanh/đỏ khi tiếp nhận hồ sơ.

Spec: docs/superpowers/specs/2026-07-19-intake-routing-design.md §4.

"Planner Agent" trong ảnh nghiệp vụ là một luật phân loại, KHÔNG phải mô
hình ngôn ngữ — giữ tất định để demo lặp lại được (PRD 14.4).

Thuần hàm, không chạm DB và không import gì từ `api`, nên worker hoặc một
service khác dùng lại được y nguyên mà không kéo theo tầng web.
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.constants import (
    AUTO_APPROVAL_CEILING_VND,
    AUTO_APPROVAL_ELIGIBLE_PRODUCTS,
    AUTO_APPROVAL_SEGMENT,
)

GREEN = "GREEN"
RED = "RED"


@dataclass(frozen=True)
class RoutingResult:
    lane: str
    reason: str


def _vnd(amount: int) -> str:
    """8000000000 -> '8.000.000.000' — dấu chấm là quy ước tiếng Việt."""
    return f"{amount:,}".replace(",", ".")


def classify_lane(*, product: str, segment: str, amount_vnd: int) -> RoutingResult:
    """Phân luồng một hồ sơ vừa tiếp nhận.

    Luồng xanh cần đủ CẢ BA điều kiện; thiếu bất kỳ điều nào là luồng đỏ.
    `reason` nói rõ điều kiện nào trượt, vì màn hình demo hiển thị lý do
    chứ không chỉ hiển thị nhãn — và vì audit cần biết vì sao.
    """
    if product not in AUTO_APPROVAL_ELIGIBLE_PRODUCTS:
        return RoutingResult(RED, f"sản phẩm {product} không thuộc diện tự động phê duyệt")

    if segment != AUTO_APPROVAL_SEGMENT:
        return RoutingResult(RED, f"phân khúc {segment} không phải {AUTO_APPROVAL_SEGMENT}")

    if amount_vnd > AUTO_APPROVAL_CEILING_VND:
        return RoutingResult(
            RED,
            f"{_vnd(amount_vnd)} vượt hạn mức tự động {_vnd(AUTO_APPROVAL_CEILING_VND)}",
        )

    return RoutingResult(
        GREEN,
        f"{product}, {segment}, {_vnd(amount_vnd)} ≤ {_vnd(AUTO_APPROVAL_CEILING_VND)}",
    )
