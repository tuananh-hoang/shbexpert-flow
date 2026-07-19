"""Redis queue/pub-sub naming shared by `api` (producer) and `worker`
(consumer) — kept in one place so the two processes can't drift apart on
the literal string and silently stop talking to each other."""
from __future__ import annotations

ANALYZE_QUEUE = "analyze_queue"


def progress_channel(case_id: str) -> str:
    return f"case:{case_id}:progress"


# ---------------------------------------------------------------------------
# Luồng xanh (ACAS-SLINK) — hàng đợi và kênh tiến trình riêng.
#
# Kênh khoá theo slink_application_id, KHÔNG theo case_id: luồng xanh không
# sinh ra case nào. Đây là hệ quả trực tiếp của quyết định tách domain ở
# docs/superpowers/specs/2026-07-19-intake-routing-design.md §2.
# ---------------------------------------------------------------------------
SLINK_SCORING_QUEUE = "slink_scoring_queue"


def slink_progress_channel(slink_application_id: str) -> str:
    return f"slink:{slink_application_id}:progress"
