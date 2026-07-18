"""Chạy pipeline multi-agent THẬT (LangGraph) trên bộ 24 golden case, k lần
mỗi case, ghi eval/multi_agent/results/metrics.jsonl.

Cần Postgres + Redis + 3 MCP server đọc. Chạy trong network của compose:

    docker compose up -d
    docker compose stop worker          # BẮT BUỘC: xem ghi chú "đua" bên dưới

    # 1) Seed 24 case (idempotent) — chạy qua `api` vì chỉ image api có gói
    #    `minio` mà scripts/seed_synthetic_cases.py cần để render/upload PDF:
    docker compose run --rm -v ./artifacts:/app/artifacts -v ./eval:/app/eval \
        api python -m eval.multi_agent.seed

    # 2) Chạy pipeline thật — image worker mới có langgraph + MCP client:
    docker compose run --rm -v ./eval:/app/eval -v ./artifacts:/app/artifacts \
        worker python -m eval.multi_agent.run_case

Vì sao phải `docker compose stop worker`: service worker chạy nền tiêu thụ
`analyze_queue` với LLM_MOCK=true theo .env. Ở lần chạy eval đầu tiên nó đã
giành mất 4 case và xử lý bằng LLM giả TRƯỚC khi script này kịp chạy; gọi lại
ainvoke() trên một thread_id đã hoàn tất chỉ phát lại checkpoint cũ trong tích
tắc chứ không chạy lại node nào, nên llm_call_count về 0 — số liệu không thật.

pass^k: mỗi lượt lặp dùng thread_id riêng (`<case_id>-r<rep>`) để tránh đúng cái
bẫy phát-lại-checkpoint đó; nếu dùng lại thread_id cũ thì lượt 2 và 3 sẽ chỉ là
bản sao của lượt 1 và chỉ số ổn định sẽ luôn đẹp một cách giả tạo.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from sqlalchemy import select

from app.graph.build import Checkpointer, build_compiled_graph
from app.llm import adapter

from shared.db import get_session
from shared.models import Case, ConflictRecord, DecisionPackage, Event, Finding

from eval.common.io import write_jsonl
from eval.common.scoring import (DOMAINS, load_golden, score_conflict,
                                 score_decision, score_numbers, score_risks)

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "metrics.jsonl"
K = int(os.environ.get("EVAL_K", "3"))

# (agent_id, metrics key) -> khoá trong ground_truth_numbers. Các con số này do
# mcp-deterministic tính (không phải LLM tự nhẩm), nên đây chính là chỗ kỳ vọng
# multi-agent hơn hẳn về độ chính xác số học.
#
# PHẢI phân biệt theo agent_id: Financial và Collateral CÙNG ghi khoá
# `coverage_ratio` nhưng KHÁC nghĩa — Financial là giá trị định giá khách nộp /
# hạn mức (naive), Collateral là giá trị thanh lý sau haircut / TỔNG nghĩa vụ.
# Đó chính là cặp số tạo ra mâu thuẫn liên agent có chủ đích, nên gộp chung một
# khoá sẽ bốc nhầm số và báo sai lệch độ chính xác.
METRIC_TO_TRUTH = {
    ("financial_analysis", "dscr"): "dscr",
    ("financial_analysis", "coverage_ratio"): "coverage_ratio_naive",
    ("collateral_legal", "coverage_ratio"): "coverage_ratio_after_haircut",
    ("financial_analysis", "debt_ratio"): "debt_ratio",
    ("financial_analysis", "current_ratio"): "current_ratio",
}


def _snapshot(case_id: str) -> dict:
    """Đọc kết quả 1 lượt chạy từ Postgres: finding mới nhất mỗi finding_key,
    conflict, decision, số event."""
    with get_session() as session:
        rows = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
        latest: dict[str, Finding] = {}
        for f in rows:
            cur = latest.get(f.finding_key)
            if cur is None or f.version > cur.version:
                latest[f.finding_key] = f
        findings = [
            {"agent_id": f.agent_id, "issue_key": f.issue_key, "stance": f.stance,
             "evidence_ids": list(f.evidence_ids or []), "metrics": dict(f.metrics or {})}
            for f in latest.values()
        ]
        conflicts = session.execute(
            select(ConflictRecord).where(ConflictRecord.case_id == case_id)).scalars().all()
        decision = session.execute(
            select(DecisionPackage).where(DecisionPackage.case_id == case_id)
            .order_by(DecisionPackage.version.desc())).scalars().first()
        events = session.execute(select(Event).where(Event.case_id == case_id)).scalars().all()
        return {
            "findings": findings,
            "conflict_detected": len(conflicts) > 0,
            "conflict_rounds": max((c.round for c in conflicts), default=0),
            "decision": decision.recommendation if decision else None,
            "event_count": len(events),
        }


def _case_exists(case_id: str) -> bool:
    with get_session() as session:
        return session.get(Case, case_id) is not None


async def _run_once(case_id: str, golden_row: dict, graph, rep: int) -> dict:
    collector: list[dict] = []
    adapter.set_metrics_collector(collector)
    start = time.monotonic()
    error = None
    try:
        await graph.ainvoke(
            {"case_id": case_id, "as_of_date": "", "findings_written": []},
            config={"configurable": {"thread_id": f"{case_id}-r{rep}"}},
        )
    except Exception as exc:  # noqa: BLE001 -- ghi lại rồi chạy tiếp, không mất các case khác
        error = f"{type(exc).__name__}: {exc}"
    wall_ms = (time.monotonic() - start) * 1000
    adapter.set_metrics_collector(None)

    snap = _snapshot(case_id)
    findings = snap["findings"]
    flagged = {f["issue_key"] for f in findings if f["stance"] in ("CAUTION", "OPPOSE", "NEED_DATA")}
    with_evidence = sum(1 for f in findings if f["evidence_ids"])

    stated: dict[str, float] = {}
    for f in findings:
        for mk, value in f["metrics"].items():
            tk = METRIC_TO_TRUTH.get((f["agent_id"], mk))
            if tk and isinstance(value, (int, float)):
                stated.setdefault(tk, value)

    prompt_t = [c["prompt_tokens"] for c in collector if c["prompt_tokens"] is not None]
    completion_t = [c["completion_tokens"] for c in collector if c["completion_tokens"] is not None]

    return {
        "case_id": case_id,
        "archetype": golden_row.get("archetype"),
        "variant": "multi_agent",
        "rep": rep,
        "wall_clock_ms": round(wall_ms, 1),
        "llm_call_count": len(collector),
        "tokens_total": (sum(prompt_t) + sum(completion_t)) if prompt_t and completion_t else None,
        # Ước lượng CHẶN DƯỚI, không phải đếm chính xác: mỗi Finding đều đi qua
        # >=1 lệnh gọi tool MCP trước khi LLM diễn giải (xem worker/app/agents/*).
        "tool_call_count": len(findings),
        "predicted_decision": snap["decision"],
        **score_decision(golden_row, snap["decision"]),
        **score_risks(golden_row, flagged),
        **score_numbers(golden_row, stated),
        **score_conflict(golden_row, snap["conflict_detected"]),
        "flagged_risks": sorted(flagged),
        "finding_count": len(findings),
        "evidence_coverage_ratio": round(with_evidence / len(findings), 3) if findings else None,
        "conflict_detected": snap["conflict_detected"],
        "conflict_rounds": snap["conflict_rounds"],
        "domain_coverage": {d: any(f["agent_id"] == d for f in findings) for d in DOMAINS},
        "event_trace_depth": snap["event_count"],
        "error": error,
    }


async def main() -> None:
    golden = load_golden()
    missing = [cid for cid in golden if not _case_exists(cid)]
    if missing:
        raise SystemExit(f"Chưa seed {len(missing)} case: {missing[:5]}... — xem docstring, bước 1.")

    records = []
    async with Checkpointer() as saver:
        graph = await build_compiled_graph(saver)
        for case_id, row in golden.items():
            for rep in range(1, K + 1):
                rec = await _run_once(case_id, row, graph, rep)
                records.append(rec)
                print(f"[multi] {case_id} rep{rep} {row['archetype']:22} "
                      f"decision={rec['predicted_decision']} ok={rec['decision_correct']} "
                      f"recall={rec['risk_recall']} num_acc={rec['numeric_accuracy']} "
                      f"conflict={rec['conflict_detected']} err={rec['error']}")

    write_jsonl(RESULTS_PATH, records)
    print(f"[multi] wrote {len(records)} records -> {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
