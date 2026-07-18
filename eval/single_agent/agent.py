"""Variant A baseline (ai-architecture_v2.md §16.3) — MỘT lệnh gọi LLM duy
nhất suy luận trên toàn bộ hồ sơ: không tool, không ý kiến thứ hai, không
orchestrator.

Dùng ĐÚNG hàm `worker/app/llm/adapter.py::complete()` mà pipeline multi-agent
đang dùng (cùng model, cùng tier), nên khác biệt đo được là do KIẾN TRÚC, không
phải do model khác nhau.

Công bằng trong so sánh (quan trọng — đừng bỏ khi sửa file này):
  - Prompt nêu RÕ công thức quy ước của ngân hàng (EBITDA, nghĩa vụ trả nợ năm)
    vì đó là thông tin mà phía multi-agent được "biết" sẵn qua tool xác định.
    Không nêu thì bài kiểm tra số học sẽ bất công với single-agent.
  - Danh sách issue_key hợp lệ cũng được nêu, để hai bên dùng cùng từ vựng khi
    chấm risk_recall — nếu không, single-agent bị trừ điểm chỉ vì đặt tên rủi
    ro khác chứ không phải vì bỏ sót rủi ro.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKER_ROOT = _REPO_ROOT / "worker"
if str(_WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKER_ROOT))

from app.llm import adapter  # noqa: E402 -- import sau khi vá sys.path ở trên

CASES_DIR = _REPO_ROOT / "artifacts" / "eval_cases"

# Cùng từ vựng issue_key với worker/app/agents/*.py
ISSUE_KEYS = [
    "REPAYMENT_CAPACITY", "COLLATERAL_COVERAGE", "COLLATERAL_OWNERSHIP",
    "COLLATERAL_LEGAL_CHECKLIST", "REVENUE_RECONCILIATION", "CREDIT_CONDUCT",
    "CASHFLOW_QUALITY", "RELATED_PARTY_CONCENTRATION",
    "LIQUIDITY", "PROFITABILITY", "LEVERAGE", "ACTIVITY",
]

SYSTEM_PROMPT = f"""Bạn là MỘT chuyên viên thẩm định tín dụng duy nhất, tự mình phụ trách toàn bộ hồ sơ vay SME: phân tích tài chính, đối chiếu chính sách, thẩm định tài sản bảo đảm, và tra cứu quan hệ tín dụng khách hàng. Không có đồng nghiệp nào kiểm tra lại kết quả của bạn.

QUY ƯỚC TÍNH TOÁN CỦA NGÂN HÀNG (bắt buộc dùng đúng, không tự đổi công thức):
- EBITDA = lợi nhuận trước thuế + chi phí lãi vay
- Nghĩa vụ trả nợ hàng năm = chi phí lãi vay + (nợ dài hạn / 5)
- DSCR = EBITDA / nghĩa vụ trả nợ hàng năm
- Tỷ lệ bao phủ TSBĐ (theo giá trị khách nộp) = giá trị định giá / hạn mức đề nghị
- Tỷ lệ nợ = tổng nợ phải trả / (tổng nợ phải trả + vốn chủ sở hữu)
- Tỷ lệ thanh toán hiện hành = (tiền + phải thu + hàng tồn kho) / nợ ngắn hạn
- Chênh lệch doanh thu (%) = |doanh thu BCTC - doanh thu chịu thuế| / doanh thu BCTC * 100

NGƯỠNG THAM CHIẾU: DSCR dưới 1.3 là thiếu đệm an toàn. Chênh lệch doanh thu trên 5% là trọng yếu, cần giải trình. Khớp nhận dạng KYC/CIC dưới 90/100 thì CHƯA được coi là đã xác minh khách hàng. Nợ CIC nhóm 3 trở lên là nợ xấu.

Chỉ được kết luận dựa trên dữ liệu có trong hồ sơ, KHÔNG bịa số liệu.

Trả lời CHỈ bằng MỘT JSON object hợp lệ, không có chữ nào trước/sau JSON:
{{
  "findings": [
    {{
      "issue_key": "một trong: {', '.join(ISSUE_KEYS)}",
      "stance": "SUPPORT|CAUTION|OPPOSE|NEED_DATA",
      "severity": "INFO|LOW|MEDIUM|HIGH|CRITICAL",
      "claim": "nhận định bằng tiếng Việt",
      "evidence_field": "tên trường dữ liệu cụ thể trong hồ sơ làm căn cứ, ví dụ financials[2025].revenue"
    }}
  ],
  "so_lieu": {{
    "dscr": <số hoặc null>,
    "coverage_ratio_naive": <số hoặc null>,
    "debt_ratio": <số hoặc null>,
    "current_ratio": <số hoặc null>,
    "revenue_mismatch_pct": <số hoặc null>
  }},
  "recommendation": "APPROVE|APPROVE_WITH_CONDITIONS|REFER|REJECT|NEED_INFO",
  "rationale": "tóm tắt lý do bằng tiếng Việt"
}}
Chỉ đưa vào "findings" những rủi ro THỰC SỰ có căn cứ trong hồ sơ — nêu rủi ro không có thật cũng bị coi là sai."""


def load_case(case_id: str) -> dict[str, Any]:
    with open(CASES_DIR / case_id / "case.json", encoding="utf-8") as f:
        return json.load(f)


def build_user_prompt(case: dict[str, Any]) -> str:
    trimmed = {k: v for k, v in case.items() if k not in ("archetype", "kich_ban")}
    return (
        "Hồ sơ tín dụng cần thẩm định (JSON):\n\n"
        + json.dumps(trimmed, ensure_ascii=False, indent=2)
        + "\n\nHãy viết kết quả phân tích đúng định dạng JSON đã mô tả."
    )


def _parse_response(text: str) -> dict[str, Any]:
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        if body.startswith("json"):
            body = body[4:]
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"không tìm thấy JSON trong phản hồi: {text[:200]!r}")
    return json.loads(body[start : end + 1])


async def run_single_agent(case_id: str) -> dict[str, Any]:
    case = load_case(case_id)
    text = await adapter.complete(tier="reasoning", system=SYSTEM_PROMPT, user=build_user_prompt(case))
    try:
        parsed = _parse_response(text)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"error": str(exc), "raw_response": text[:500], "findings": [],
                "so_lieu": {}, "recommendation": None}
    parsed.setdefault("findings", [])
    parsed.setdefault("so_lieu", {})
    parsed.setdefault("recommendation", None)
    parsed["error"] = None
    return parsed
