"""Redis queue/pub-sub naming shared by `api` (producer) and `worker`
(consumer) — kept in one place so the two processes can't drift apart on
the literal string and silently stop talking to each other."""
from __future__ import annotations

ANALYZE_QUEUE = "analyze_queue"


def progress_channel(case_id: str) -> str:
    return f"case:{case_id}:progress"
