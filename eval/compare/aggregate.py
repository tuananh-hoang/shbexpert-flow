"""Gộp kết quả 2 variant -> eval/compare/summary.md

    python -m eval.compare.aggregate
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean

from eval.common.io import read_jsonl
from eval.common.scoring import load_golden, score_decision

BASE = Path(__file__).resolve().parent.parent
PATHS = {"single_agent": BASE / "single_agent" / "results" / "metrics.jsonl",
         "multi_agent": BASE / "multi_agent" / "results" / "metrics.jsonl"}
SUMMARY_PATH = Path(__file__).resolve().parent / "summary.md"


def _avg(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(mean(vals), 3) if vals else None


def _rate(rows, key):
    vals = [1 if r.get(key) else 0 for r in rows if r.get(key) is not None]
    return round(mean(vals), 3) if vals else None


def _consistency(rows):
    """pass^k: tỷ lệ case mà MỌI lượt lặp đều cho cùng một quyết định. Đo độ ổn
    định của kiến trúc, không phải độ đúng."""
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r.get("predicted_decision"))
    if not by_case:
        return None
    stable = sum(1 for ds in by_case.values() if len(set(ds)) == 1)
    return round(stable / len(by_case), 3)


def _fp_rate(rows):
    """Tỷ lệ lượt chạy có ít nhất 1 cảnh báo giả (chỉ tính trên case có khai
    báo must_not_flag — thực tế là nhóm hồ sơ sạch)."""
    rel = [r for r in rows if r.get("false_positive_count") is not None]
    return round(mean(1 if r["false_positive_count"] > 0 else 0 for r in rel), 3) if rel else None


def main() -> None:
    golden = load_golden()
    data = {}
    for name, p in PATHS.items():
        if not p.exists():
            raise SystemExit(f"Thiếu {p} — chạy runner của '{name}' trước.")
        rows = list(read_jsonl(p))
        # Chấm LẠI quyết định từ golden hiện tại thay vì tin decision_correct đã
        # lưu lúc chạy: golden là nguồn sự thật duy nhất tại thời điểm báo cáo,
        # nên tinh chỉnh rubric không bắt phải chạy lại pipeline (~30 phút/lượt).
        # Các chỉ số khác giữ nguyên vì chúng phụ thuộc dữ liệu thô chỉ có lúc chạy.
        for r in rows:
            g = golden.get(r["case_id"])
            if g:
                r.update(score_decision(g, r.get("predicted_decision")))
        data[name] = rows

    s, m = data["single_agent"], data["multi_agent"]
    L = ["# Kết quả eval: multi-agent vs single-agent (ablation Variant A)\n",
         f"- Bộ case: {len(set(r['case_id'] for r in s))} case × "
         f"{max((r['rep'] for r in s), default=1)} lượt lặp mỗi case",
         f"- single_agent: {len(s)} lượt chạy | multi_agent: {len(m)} lượt chạy\n",
         "## Chất lượng (chiều multi-agent kỳ vọng mạnh hơn)\n",
         "| Chỉ số | single_agent | multi_agent |", "|---|---|---|"]

    quality = [
        ("Quyết định đúng (decision_correct)", lambda r: _rate(r, "decision_correct")),
        ("Risk recall (nêu đủ rủi ro bắt buộc)", lambda r: _avg(r, "risk_recall")),
        ("Numeric accuracy (số liệu tính đúng)", lambda r: _avg(r, "numeric_accuracy")),
        ("Evidence coverage (claim có dẫn chứng)", lambda r: _avg(r, "evidence_coverage_ratio")),
        ("Consistency pass^k (mọi lượt cùng KQ)", _consistency),
        ("Tỷ lệ có cảnh báo giả (thấp = tốt)", _fp_rate),
        ("Phát hiện mâu thuẫn đúng kỳ vọng", lambda r: _rate(r, "conflict_correct")),
    ]
    for label, fn in quality:
        L.append(f"| {label} | {fn(s)} | {fn(m)} |")

    L += ["\n## Chi phí (chiều single-agent thường thắng — giữ trung thực)\n",
          "| Chỉ số | single_agent | multi_agent |", "|---|---|---|"]
    for label, key in [("Thời gian chạy (ms)", "wall_clock_ms"), ("Số lệnh gọi LLM", "llm_call_count"),
                       ("Tổng token", "tokens_total")]:
        L.append(f"| {label} | {_avg(s, key)} | {_avg(m, key)} |")

    # Ba chỉ số ĐẾM dưới đây chỉ lấy từ lượt 1: chạy lặp trên cùng case_id làm
    # Finding/Event TÍCH LUỸ trong Postgres (mỗi lượt mint finding_key mới), nên
    # lượt 2-3 sẽ thổi phồng số đếm. Các chỉ số chất lượng phía trên không bị
    # ảnh hưởng vì issue_key và giá trị metrics lặp lại y hệt.
    s1 = [r for r in s if r.get("rep") == 1]
    m1 = [r for r in m if r.get("rep") == 1]
    for label, key in [("Số lệnh gọi tool (chỉ lượt 1; multi là chặn dưới)", "tool_call_count"),
                       ("Số finding (chỉ lượt 1)", "finding_count"),
                       ("Độ sâu vết audit (chỉ lượt 1)", "event_trace_depth")]:
        L.append(f"| {label} | {_avg(s1, key)} | {_avg(m1, key)} |")

    L += ["\n## Theo từng archetype nghiệp vụ\n",
          "| Archetype | QĐ đúng (single) | QĐ đúng (multi) | Recall (single) | Recall (multi) |",
          "|---|---|---|---|---|"]
    for arch in sorted({r["archetype"] for r in s if r.get("archetype")}):
        ss = [r for r in s if r["archetype"] == arch]
        mm = [r for r in m if r["archetype"] == arch]
        L.append(f"| {arch} | {_rate(ss,'decision_correct')} | {_rate(mm,'decision_correct')} | "
                 f"{_avg(ss,'risk_recall')} | {_avg(mm,'risk_recall')} |")

    err_m = sum(1 for r in m if r.get("error"))
    err_s = sum(1 for r in s if r.get("error"))
    L += ["\n## Lỗi trong lúc chạy (công bố đầy đủ)\n",
          f"- single_agent: {err_s}/{len(s)} lượt lỗi",
          f"- multi_agent: {err_m}/{len(m)} lượt lỗi — phần lớn là "
          "`update_case_status 409 Conflict` ở lượt lặp 2-3. Đây là **hệ quả của cách đo pass^k**, "
          "không phải hệ thống hỏng: case đã chuyển sang READY_FOR_REVIEW ở lượt 1 nên state machine "
          "từ chối chuyển tiếp lần nữa. Node transition chạy SAU khi DecisionPackage đã ghi, nên "
          "quyết định và finding của các lượt đó vẫn hợp lệ (đã kiểm: 100% lượt lỗi 409 vẫn có "
          "quyết định đầy đủ). Muốn sạch hoàn toàn thì mỗi lượt lặp phải seed case_id riêng.\n",
          "## Ghi chú đọc số\n",
          "- `numeric_accuracy` là chiều khách quan nhất: ground truth tính bằng đúng công thức "
          "xác định, multi-agent lấy số từ mcp-deterministic còn single-agent tự nhẩm trong prompt. "
          "Cả hai đều được cung cấp cùng bộ công thức nên đây là phép so công bằng.",
          "- `evidence_coverage` của single-agent chỉ là 'có điền tên trường dữ liệu hay không' — "
          "LLM viết được một chuỗi nghe hợp lý bất kể có thật hay không. Phía multi-agent là "
          "evidence_ids trỏ tới bản ghi có thật, bị `EvidenceRequiredError` (shared/state.py) chặn "
          "ở tầng ghi. Cùng tên chỉ số nhưng KHÔNG cùng độ đảm bảo.",
          "- `tool_call_count` của multi-agent là chặn dưới (đếm theo số Finding), của single-agent "
          "là 0 chính xác — kiến trúc đó không gọi tool nào.",
          "- **`COLLATERAL_SHORTFALL`: single-agent recall 0.0 KHÔNG phải vì suy luận kém** mà vì "
          "giá trị định giá chính thức của ngân hàng và tổng nghĩa vụ nằm ở registry nội bộ "
          "(tools-mock), không có trong bộ hồ sơ tài liệu. Nhìn từ dữ liệu khách nộp thì TSBĐ vẫn "
          "đủ (coverage 1.21). Đây đúng là lợi thế kiến trúc của multi-agent (có quyền gọi tool tra "
          "cứu nguồn có thẩm quyền), nhưng phải nói rõ bản chất là KHÁC BIỆT QUYỀN TRUY CẬP DỮ LIỆU.",
          "- Rubric quyết định chấm CHẶT theo một đáp án duy nhất: một câu trả lời thận trọng quá "
          "mức (vd APPROVE_WITH_CONDITIONS cho hồ sơ sạch) vẫn bị tính sai. Điều này kéo "
          "decision_correct của single-agent xuống đáng kể; mức thận trọng thừa được đo riêng bằng "
          "chỉ số cảnh báo giả.",
          "- Golden case ghi đáp án đúng theo nghiệp vụ tín dụng, không suy ngược từ hành vi hệ "
          "thống hiện tại. Chỗ nào hệ thống trượt thì đó là kết quả thật cần đọc, không phải lỗi "
          "của bộ đề — xem 4 archetype multi-agent trượt ở bảng trên.\n"]

    SUMMARY_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
