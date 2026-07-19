"""Client gọi slink-mock từ `api`.

`api` chỉ cần biết khách hàng CÓ lịch sử SLINK hay không (200/404) lúc
tiếp nhận — `worker` mới đọc đầy đủ chuỗi dòng tiền để chấm điểm. Cùng một
endpoint phục vụ cả hai, chỉ khác cách dùng kết quả.

Spec: docs/superpowers/specs/2026-07-19-slink-scoring-design.md §3.2
"""
from __future__ import annotations

import os

import httpx

SLINK_MOCK_URL = os.environ.get("SLINK_MOCK_URL", "http://slink-mock:8400")


class SlinkUnavailableError(RuntimeError):
    """slink-mock không gọi được — sự cố hạ tầng, KHÁC với 404.

    Phân biệt hai chuyện này là có chủ đích (spec §3.5): 404 nghĩa là khách
    chưa có lịch sử SLINK, hợp lệ về nghiệp vụ, hạ xuống luồng đỏ. Còn
    không gọi được service thì phải báo 502 — âm thầm đẩy mọi hồ sơ thấu
    chi sang luồng đỏ sẽ làm outage trở nên vô hình, hệ thống trông vẫn
    đúng trong khi toàn bộ tự động hoá đã tắt.
    """


def merchant_exists(customer_id: str, *, timeout_seconds: float = 5.0) -> bool:
    try:
        response = httpx.get(
            f"{SLINK_MOCK_URL}/slink/merchants/{customer_id}", timeout=timeout_seconds
        )
    except httpx.HTTPError as exc:
        raise SlinkUnavailableError(f"không gọi được slink-mock: {exc}") from exc

    if response.status_code == 404:
        return False
    if response.status_code != 200:
        raise SlinkUnavailableError(f"slink-mock trả {response.status_code}")
    return True
