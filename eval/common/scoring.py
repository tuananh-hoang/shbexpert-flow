"""Chấm điểm dùng CHUNG cho cả hai variant — áp dụng y hệt nhau để phép so
sánh không bị lệch do một bên tự chấm mình dễ hơn bên kia.

Bộ metric (xem eval/README.md để biết vì sao chọn các chiều này):
  - decision_correct     : quyết định có đúng hướng nghiệp vụ không
  - risk_recall          : các rủi ro BẮT BUỘC phải nêu, nêu được bao nhiêu %
  - false_positive       : có bịa rủi ro không đáng có không
  - numeric_accuracy     : con số nêu ra có khớp giá trị tính bằng công thức
                           xác định không (multi-agent lấy từ tool, single-agent
                           tự tính trong đầu)
  - evidence_grounding   : claim có trỏ tới bằng chứng CÓ THẬT không
  - conflict_handling    : có phát hiện mâu thuẫn liên agent khi cần không
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.common.io import read_jsonl

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "golden_cases.jsonl"

# 4 agent_id thật (worker/app/agents/*.py::AGENT_ID)
DOMAINS = ["financial_analysis", "policy_compliance", "collateral_legal", "customer_360"]

# Sai số cho phép khi đối chiếu số: 1% tương đối. Nới hơn 0 vì single-agent
# thường làm tròn khi diễn giải (vd "khoảng 1,05"), và mục tiêu đo là "có tính
# đúng bản chất không", không phải bắt lỗi chữ số thập phân.
NUMERIC_TOLERANCE = 0.01


def load_golden() -> dict[str, dict[str, Any]]:
    return {row["case_id"]: row for row in read_jsonl(GOLDEN_PATH)}


def score_decision(golden_row: dict, predicted: str | None) -> dict:
    """Chấm CHẶT theo MỘT đáp án duy nhất: mỗi case có đúng một
    `expected_decision` suy từ logic rủi ro tín dụng, khớp chính xác mới tính
    đúng.

    Rubric đơn trị này áp dụng như nhau cho cả hai variant và KHÔNG tự động
    thiên vị multi-agent: scorecard hiện tại không có hard gate cho nợ CIC
    nhóm 3+, định giá hết hiệu lực, DSCR yếu hay đòn bẩy cao, nên chính
    pipeline multi-agent cũng trượt các archetype đó. Đọc số cần nhớ: một đáp
    án "thận trọng quá mức" (vd APPROVE_WITH_CONDITIONS cho hồ sơ sạch) cũng
    bị tính là sai — mức độ thận trọng thừa được đo riêng bằng
    false_positive_count."""
    expected = golden_row.get("expected_decision")
    if predicted is None:
        return {"decision_correct": False, "decision_reason": "không có quyết định"}
    if predicted != expected:
        return {"decision_correct": False, "decision_reason": f"kỳ vọng {expected}, nhận {predicted}"}
    return {"decision_correct": True, "decision_reason": None}


# Chuẩn hoá từ đồng nghĩa về issue_key chuẩn. Chỉ có LỢI cho single-agent
# (multi-agent vốn ghi thẳng issue_key chuẩn vào DB), nên bảng này làm phép so
# CÔNG BẰNG HƠN chứ không nghiêng về multi-agent: mục tiêu của risk_recall là
# đo "có phát hiện ra rủi ro không", không phải đo "có thuộc từ vựng không".
# Quan sát thật: single-agent nhận đúng vấn đề nhận dạng KYC nhưng đặt tên
# issue_key là "KYC" thay vì CREDIT_CONDUCT.
ISSUE_KEY_ALIASES = {
    "KYC": "CREDIT_CONDUCT",
    "KYC_AML": "CREDIT_CONDUCT",
    "IDENTITY": "CREDIT_CONDUCT",
    "IDENTITY_VERIFICATION": "CREDIT_CONDUCT",
    "CIC": "CREDIT_CONDUCT",
    "CREDIT_HISTORY": "CREDIT_CONDUCT",
    "COLLATERAL": "COLLATERAL_COVERAGE",
    "COLLATERAL_VALUE": "COLLATERAL_COVERAGE",
    "COLLATERAL_VALUATION": "COLLATERAL_COVERAGE",
    "VALUATION": "COLLATERAL_COVERAGE",
    "REVENUE_MISMATCH": "REVENUE_RECONCILIATION",
    "REVENUE": "REVENUE_RECONCILIATION",
    "TAX_RECONCILIATION": "REVENUE_RECONCILIATION",
    "DSCR": "REPAYMENT_CAPACITY",
    "REPAYMENT": "REPAYMENT_CAPACITY",
    "SOLVENCY": "LEVERAGE",
    "DEBT_RATIO": "LEVERAGE",
    "CASHFLOW": "CASHFLOW_QUALITY",
}


def normalize_issue_keys(keys) -> set[str]:
    out = set()
    for k in keys:
        if not k:
            continue
        u = str(k).strip().upper().replace(" ", "_").replace("-", "_")
        out.add(ISSUE_KEY_ALIASES.get(u, u))
    return out


def score_risks(golden_row: dict, flagged_issue_keys: set[str]) -> dict:
    """risk_recall: trong các rủi ro bắt buộc, nêu được bao nhiêu.
    false_positive: có nêu rủi ro nằm trong danh sách 'không được nêu' không
    (dùng cho hồ sơ sạch — đo xu hướng bịa rủi ro)."""
    must = normalize_issue_keys(golden_row.get("must_flag_risks") or [])
    must_not = normalize_issue_keys(golden_row.get("must_not_flag_risks") or [])
    flagged_issue_keys = normalize_issue_keys(flagged_issue_keys)

    hit = must & flagged_issue_keys
    recall = round(len(hit) / len(must), 3) if must else None
    fp = must_not & flagged_issue_keys
    return {
        "risk_recall": recall,
        "risks_missed": sorted(must - flagged_issue_keys),
        "false_positive_count": len(fp),
        "false_positives": sorted(fp),
    }


def score_numbers(golden_row: dict, stated: dict[str, float | None]) -> dict:
    """Đối chiếu con số hệ thống nêu ra với ground truth tính bằng đúng công
    thức tool xác định. Chỉ chấm những khoá thực sự có nêu — không nêu thì
    không tính là sai (đo độ CHÍNH XÁC của số đã nêu, không phải độ đầy đủ;
    độ đầy đủ đã có risk_recall lo)."""
    truth = golden_row.get("ground_truth_numbers") or {}
    checked, correct, details = 0, 0, {}
    for key, value in stated.items():
        if value is None or key not in truth or truth[key] in (None, 0):
            continue
        checked += 1
        expected = truth[key]
        ok = abs(value - expected) / abs(expected) <= NUMERIC_TOLERANCE
        correct += 1 if ok else 0
        details[key] = {"stated": value, "expected": expected, "ok": ok}
    return {
        "numeric_checked": checked,
        "numeric_correct": correct,
        "numeric_accuracy": round(correct / checked, 3) if checked else None,
        "numeric_detail": details,
    }


def score_conflict(golden_row: dict, conflict_detected: bool) -> dict:
    expected = golden_row.get("expected_conflict")
    if expected is None:
        return {"conflict_expected": None, "conflict_correct": None}
    return {"conflict_expected": expected, "conflict_correct": conflict_detected == expected}


def domain_coverage(domains_present: set[str]) -> dict[str, bool]:
    return {d: d in domains_present for d in DOMAINS}


def evidence_coverage_ratio(total: int, with_evidence: int) -> float | None:
    return round(with_evidence / total, 3) if total else None
