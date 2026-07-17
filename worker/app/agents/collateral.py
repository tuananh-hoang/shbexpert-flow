"""Collateral & Legal Agent — ai-architecture.md §5.4.

Tool allowlist: mcp-deterministic (calculate_coverage) + mcp-rag
(search_legal_checklist) + mcp-external (get_valuation) — a THIRD, distinct
combination from Financial (mcp-deterministic only) and Policy (mcp-rag
only), which is exactly what data-flow.md §11's demo checklist asks for:
"Ba agent có chuyên môn và tool khác nhau — không phải ba prompt giống nhau".

Deliberately more rigorous than Financial's naive coverage check
(financial.py::_collateral_coverage_finding): uses the bank's OWN
valuation-on-file (mcp-external) instead of the customer's submitted
number, and checks the submitted certificate's expiry against the legal
checklist's minimum-validity rule. Same issue_key (COLLATERAL_COVERAGE),
same calculate_coverage tool, different diligence — realistic material
for Phase 4's conflict detector.

DB access goes through common.run_sync(...) — see the comment on that
function for the deadlock this avoids under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from datetime import date

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import read_extracted_fields_sync, read_requested_facility_sync, run_sync, unwrap_mcp_result, write_finding_sync
from app.config import MCP_DETERMINISTIC_URL, MCP_EXTERNAL_URL, MCP_RAG_URL
from app.llm.adapter import complete
from shared.schemas import Citation, FindingIn, FindingOut

AGENT_ID = "collateral_legal"
ISSUE_KEY = "COLLATERAL_COVERAGE"
COLLATERAL_TYPE = "valuation_certificate"

# Matches the seeded legal_checklist clause's own wording ("toi thieu 60
# ngay"). Mock ground truth, not an SHB legal requirement.
_MIN_DAYS_BEFORE_EXPIRY = 60


def _mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "deterministic": {"url": MCP_DETERMINISTIC_URL, "transport": "streamable_http"},
            "rag": {"url": MCP_RAG_URL, "transport": "streamable_http"},
            "external": {"url": MCP_EXTERNAL_URL, "transport": "streamable_http"},
        }
    )


async def run_collateral_agent(
    case_id: str,
    as_of_date: str,
    *,
    finding_key: str | None = None,
    change_reason: str | None = None,
    targeted_question: str | None = None,
) -> FindingOut:
    """`finding_key` + `change_reason` are set when the Orchestrator is
    re-invoking this agent after a targeted question (ai-architecture.md
    §9.2) — the prior finding is never overwritten, this call produces the
    next version. `targeted_question` is folded into the LLM prompt so the
    claim text acknowledges what was specifically asked, but the underlying
    calculate_coverage/search_legal_checklist calls are unchanged: this
    agent's stance is driven by a hard checklist rule (valuation expiry),
    not a soft judgment call, so re-running it is a genuine re-confirmation
    with fresh reasoning, not a rubber-stamp repeat."""
    fields = await run_sync(read_extracted_fields_sync, case_id)
    requested_facility = await run_sync(read_requested_facility_sync, case_id)
    requested_amount = requested_facility["amount_vnd"]
    valuation_expiry = fields["valuation_expiry_date"]["value"]["date"]
    evidence_ids = [fields["valuation_amount"]["evidence_id"], fields["valuation_expiry_date"]["evidence_id"]]

    client = _mcp_client()
    tools = {t.name: t for t in await client.get_tools()}

    legal = unwrap_mcp_result(
        await tools["search_legal_checklist"].ainvoke(
            {
                "collateral_type": COLLATERAL_TYPE,
                "query": "chứng thư định giá còn hiệu lực bao nhiêu ngày trước khi giải ngân",
                "top_k": 1,
            }
        )
    )
    checklist_text = legal["results"][0]["text"]
    citation = Citation(
        source_type="LEGAL_CHECKLIST",
        source_id=COLLATERAL_TYPE,
        version=str(legal["results"][0].get("version")) if legal["results"][0].get("version") is not None else None,
        text=checklist_text,
        score=legal["results"][0]["score"],
    )

    official = unwrap_mcp_result(await tools["get_valuation"].ainvoke({"collateral_id": case_id}))
    official_value = official["official_value_vnd"]

    coverage = unwrap_mcp_result(
        await tools["calculate_coverage"].ainvoke(
            {"eligible_value": official_value, "requested_amount": requested_amount}
        )
    )
    coverage_ratio = coverage["outputs"]["coverage_ratio"]
    formula_version = coverage["formula_version"]

    days_to_expiry = (date.fromisoformat(valuation_expiry) - date.fromisoformat(as_of_date[:10])).days
    expiry_ok = days_to_expiry >= _MIN_DAYS_BEFORE_EXPIRY

    # Expiry rule dominates: even a comfortable coverage ratio doesn't
    # matter if the certificate itself won't be valid long enough — the
    # checklist requires a fresh valuation before disbursement either way.
    stance = "SUPPORT" if expiry_ok else "CAUTION"
    severity = "MEDIUM" if expiry_ok else "HIGH"
    recommended_action = None if expiry_ok else "REQUIRE_REVALUATION"

    question_context = (
        f"\n\nCâu hỏi từ Orchestrator: \"{targeted_question}\" — hãy trả lời thẳng vào câu hỏi này "
        f"trong claim, dựa trên cùng dữ liệu và checklist ở trên."
        if targeted_question
        else ""
    )
    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Collateral & Legal Agent. Bạn CHỈ diễn giải kết quả đã tính (coverage "
            "ratio) và nội dung checklist pháp lý đã tra cứu — không tự tính lại số liệu "
            "hay tạo ngoại lệ ngoài checklist."
        ),
        user=(
            f"Coverage ratio (dùng giá trị định giá nội bộ ngân hàng): {coverage_ratio} "
            f"(formula_version={formula_version}). Chứng thư định giá còn {days_to_expiry} "
            f"ngày hiệu lực tính đến ngày hồ sơ. Checklist pháp lý: \"{checklist_text}\". "
            f"Viết 1-2 câu claim tiếng Việt nêu rõ tài sản bảo đảm có đạt yêu cầu giải ngân "
            f"hay cần định giá lại.{question_context}"
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY,
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=evidence_ids,
        citations=[citation],
        confidence=0.9,
        recommended_action=recommended_action,
        change_reason=change_reason,
    )
    return await run_sync(
        write_finding_sync, finding, finding_key=finding_key, versions={"formula_version": formula_version}
    )
