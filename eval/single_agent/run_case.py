"""Chạy baseline single-agent (Variant A) trên bộ 24 golden case, k lần mỗi
case, ghi eval/single_agent/results/metrics.jsonl.

Không cần Postgres/Redis/MCP — chạy thẳng từ host:
    python -m eval.single_agent.run_case            # k=3 (mặc định)
    EVAL_K=1 python -m eval.single_agent.run_case   # chạy nhanh 1 lượt
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from eval.single_agent.agent import run_single_agent  # vá sys.path cho worker/ như tác dụng phụ
from app.llm import adapter  # noqa: E402 -- chỉ import được sau dòng trên

from eval.common.io import write_jsonl
from eval.common.scoring import (load_golden, score_conflict, score_decision,
                                 score_numbers, score_risks)

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "metrics.jsonl"
K = int(os.environ.get("EVAL_K", "3"))


async def _run_once(case_id: str, golden_row: dict, rep: int) -> dict:
    collector: list[dict] = []
    adapter.set_metrics_collector(collector)
    start = time.monotonic()
    result = await run_single_agent(case_id)
    wall_ms = (time.monotonic() - start) * 1000
    adapter.set_metrics_collector(None)

    findings = [f for f in result.get("findings", []) if isinstance(f, dict)]
    # Chỉ tính là "nêu rủi ro" khi stance KHÁC SUPPORT — một finding SUPPORT là
    # "chỗ này ổn", không phải cảnh báo. Cùng quy ước với phía multi-agent.
    flagged = {f.get("issue_key") for f in findings
               if f.get("issue_key") and f.get("stance") in ("CAUTION", "OPPOSE", "NEED_DATA")}
    with_evidence = sum(1 for f in findings if f.get("evidence_field"))

    so_lieu = result.get("so_lieu") or {}
    stated = {k: v for k, v in so_lieu.items() if isinstance(v, (int, float))}

    predicted = result.get("recommendation")
    prompt_t = [c["prompt_tokens"] for c in collector if c["prompt_tokens"] is not None]
    completion_t = [c["completion_tokens"] for c in collector if c["completion_tokens"] is not None]

    return {
        "case_id": case_id,
        "archetype": golden_row.get("archetype"),
        "variant": "single_agent",
        "rep": rep,
        "wall_clock_ms": round(wall_ms, 1),
        "llm_call_count": len(collector),
        "tokens_total": (sum(prompt_t) + sum(completion_t)) if prompt_t and completion_t else None,
        "tool_call_count": 0,  # chính xác tuyệt đối: kiến trúc này không gọi tool nào
        "predicted_decision": predicted,
        **score_decision(golden_row, predicted),
        **score_risks(golden_row, flagged),
        **score_numbers(golden_row, stated),
        **score_conflict(golden_row, conflict_detected=False),
        "flagged_risks": sorted(flagged),
        "finding_count": len(findings),
        "evidence_coverage_ratio": round(with_evidence / len(findings), 3) if findings else None,
        "event_trace_depth": len(findings) + (1 if predicted else 0),
        "error": result.get("error"),
    }


async def main() -> None:
    if os.environ.get("LLM_MOCK", "false").lower() in ("1", "true", "yes"):
        print("CẢNH BÁO: LLM_MOCK=true — số liệu latency/token vô nghĩa. Đặt LLM_MOCK=false để chạy thật.")

    golden = load_golden()
    records = []
    for case_id, row in golden.items():
        for rep in range(1, K + 1):
            rec = await _run_once(case_id, row, rep)
            records.append(rec)
            print(f"[single] {case_id} rep{rep} {row['archetype']:22} "
                  f"decision={rec['predicted_decision']} ok={rec['decision_correct']} "
                  f"recall={rec['risk_recall']} num_acc={rec['numeric_accuracy']} "
                  f"err={rec['error']}")

    write_jsonl(RESULTS_PATH, records)
    print(f"[single] wrote {len(records)} records -> {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
