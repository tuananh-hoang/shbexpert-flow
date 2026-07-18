"""Collateral & Legal Agent — ai-architecture.md §5.4.

Tool allowlist: mcp-deterministic (calculate_coverage, calculate_collateral_coverage)
+ mcp-rag (search_legal_checklist) + mcp-external (get_valuation, get_credit_obligations)
— a THIRD, distinct combination from Financial (mcp-deterministic only) and
Policy (mcp-rag only), which is exactly what data-flow.md §11's demo checklist
asks for: "Ba agent có chuyên môn và tool khác nhau — không phải ba prompt
giống nhau".

Writes THREE findings (`run_collateral_agent` returns a list now — see
graph/build.py::_collateral_node):
  - COLLATERAL_COVERAGE — deliberately more rigorous than Financial's naive
    coverage check (financial.py::_collateral_coverage_finding): uses the
    bank's OWN valuation (get_valuation, enriched with haircut/forced_sale
    value), the customer's FULL obligation exposure (get_credit_obligations),
    AND two INDEPENDENT staleness rules (see below). Same issue_key, same
    "coverage" concept, more diligence — realistic material for Phase 4's
    conflict detector.
  - COLLATERAL_OWNERSHIP — validate_ownership (common.py, direct Postgres
    read, not an MCP tool — see shared/models.py's "Collateral & Legal
    domain" section for why).
  - COLLATERAL_LEGAL_CHECKLIST — search_legal_checklist (semantic hits)
    joined with legal_checklist_template/regulatory_reference/
    checklist_completion (structured, Postgres) by checklist_id.

Two INDEPENDENT "hết hạn" rules, deliberately kept separate so they're never
confused (see plan's Rủi ro note):
  - `cert_days_to_expiry` / `_MIN_DAYS_BEFORE_EXPIRY` — the CUSTOMER-submitted
    valuation certificate's own stated expiry_date (extracted_fields).
  - `report_is_stale` — the BANK's own valuation report (get_valuation)
    going stale 12 months after its valuation_date (report_expiry_date,
    baked into tools-mock's mock data, not recomputed here).
Either one failing outweighs a comfortable coverage_ratio — the checklist
requires a fresh, valid instrument before disbursement regardless of value.

DB access goes through common.run_sync(...) — see the long comment on that
function for the deadlock this avoids under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from datetime import date

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import (
    read_case_customer_id_sync,
    read_checklist_items_sync,
    read_extracted_fields_sync,
    read_haircut_rate_sync,
    read_requested_facility_sync,
    run_sync,
    unwrap_mcp_result,
    validate_ownership_sync,
    write_finding_sync,
)
from app.config import MCP_DETERMINISTIC_URL, MCP_EXTERNAL_URL, MCP_RAG_URL
from app.llm.adapter import complete
from shared.schemas import Citation, FindingIn, FindingOut

AGENT_ID = "collateral_legal"
COVERAGE_ISSUE_KEY = "COLLATERAL_COVERAGE"
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
    calculate_collateral_coverage/search_legal_checklist calls are unchanged:
    this agent's stance is driven by hard rules (coverage tier + two expiry
    checks), not a soft judgment call, so re-running it is a genuine
    re-confirmation with fresh reasoning, not a rubber-stamp repeat."""
    fields = await run_sync(read_extracted_fields_sync, case_id)
    requested_facility = await run_sync(read_requested_facility_sync, case_id)
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    requested_amount = requested_facility["amount_vnd"]
    cert_expiry_date = fields["valuation_expiry_date"]["value"]["date"]
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

    valuation = unwrap_mcp_result(await tools["get_valuation"].ainvoke({"collateral_id": case_id}))
    forced_sale_value = valuation["forced_sale_value"]
    report_expiry_date = valuation["report_expiry_date"]

    haircut_rate = await run_sync(read_haircut_rate_sync, COLLATERAL_TYPE)
    if haircut_rate is None:
        haircut_rate = 0.0  # no matching haircut_matrix row — conservative fallback, not a crash

    obligations = unwrap_mcp_result(await tools["get_credit_obligations"].ainvoke({"customer_id": customer_id}))
    # Coverage must hold against the FULL post-disbursement exposure — the
    # customer's existing obligations PLUS the facility being requested now
    # — not just what's already on the books (cẩm nang trang 25's logic,
    # extended to "what coverage looks like after this loan disburses").
    total_obligation = obligations["total_obligation_vnd"] + requested_amount

    coverage = unwrap_mcp_result(
        await tools["calculate_collateral_coverage"].ainvoke(
            {"eligible_value": forced_sale_value, "haircut_rate": haircut_rate, "total_obligation": total_obligation}
        )
    )
    coverage_ratio = coverage["outputs"]["coverage_ratio"]
    coverage_tier = coverage["outputs"]["coverage_tier"]
    formula_version = coverage["formula_version"]

    cert_days_to_expiry = (date.fromisoformat(cert_expiry_date) - date.fromisoformat(as_of_date[:10])).days
    cert_expiry_ok = cert_days_to_expiry >= _MIN_DAYS_BEFORE_EXPIRY
    report_is_stale = date.fromisoformat(report_expiry_date) < date.fromisoformat(as_of_date[:10])

    if coverage_tier == "UNDER_SECURED":
        stance, severity, recommended_action = "OPPOSE", "CRITICAL", "REQUIRE_ADDITIONAL_COLLATERAL"
    elif not cert_expiry_ok or report_is_stale:
        stance, severity, recommended_action = "CAUTION", "HIGH", "REQUIRE_REVALUATION"
    elif coverage_tier == "ADEQUATE":
        stance, severity, recommended_action = "CAUTION", "MEDIUM", None
    else:  # OVER_SECURED, both expiry checks pass
        stance, severity, recommended_action = "SUPPORT", "MEDIUM", None

    question_context = (
        f"\n\nCâu hỏi từ Orchestrator: \"{targeted_question}\" — hãy trả lời thẳng vào câu hỏi này "
        f"trong claim, dựa trên cùng dữ liệu và checklist ở trên."
        if targeted_question
        else ""
    )
    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Collateral & Legal Agent. Bạn CHỈ diễn giải coverage_tier đã tính (dùng giá "
            "trị thanh lý bắt buộc sau haircut, so với TỔNG nghĩa vụ sau giải ngân) và kết quả 2 "
            "rule hiệu lực (chứng thư khách nộp, report định giá nội bộ) — không tự tính lại số "
            "liệu hay tạo ngoại lệ ngoài checklist."
        ),
        user=(
            f"coverage_ratio={coverage_ratio} (tier={coverage_tier}, formula_version={formula_version}). "
            f"Chứng thư khách nộp còn {cert_days_to_expiry} ngày hiệu lực (yêu cầu tối thiểu {_MIN_DAYS_BEFORE_EXPIRY}). "
            f"Report định giá nội bộ {'ĐÃ quá hạn' if report_is_stale else 'còn hiệu lực'} (report_expiry_date={report_expiry_date}). "
            f"Checklist pháp lý: \"{checklist_text}\". "
            f"Viết 1-2 câu claim tiếng Việt nêu rõ tài sản bảo đảm có đạt yêu cầu giải ngân hay "
            f"cần định giá lại/bổ sung tài sản.{question_context}"
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=COVERAGE_ISSUE_KEY,
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=evidence_ids,
        citations=[citation],
        metrics={
            "coverage_ratio": coverage_ratio,
            "cert_days_to_expiry": float(cert_days_to_expiry),
            "haircut_rate": haircut_rate,
            "total_obligation_vnd": float(total_obligation),
        },
        confidence=0.9,
        recommended_action=recommended_action,
        change_reason=change_reason,
    )
    return await run_sync(
        write_finding_sync, finding, finding_key=finding_key, versions={"formula_version": formula_version}
    )


async def run_ownership_check(case_id: str) -> FindingOut:
    """validate_ownership (ai-architecture.md §5.4) — direct Postgres read
    (common.py::validate_ownership_sync), no MCP tool. Writes issue_key
    COLLATERAL_OWNERSHIP, independent of COLLATERAL_COVERAGE — a case can
    have perfectly adequate coverage yet still be legally unsafe to
    disburse against (encumbered, disputed, or missing co-owner consent)."""
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    result = await run_sync(validate_ownership_sync, case_id, customer_id)

    if not result["registry_found"]:
        stance, severity, action = "NEED_DATA", "MEDIUM", "REQUEST_COLLATERAL_REGISTRY"
    elif result["encumbrance_found"]:
        stance, severity, action = "OPPOSE", "CRITICAL", "REQUIRE_LEGAL_REVIEW"
    elif not result["ownership_verified"]:
        stance, severity, action = "CAUTION", "HIGH", "REQUIRE_LEGAL_REVIEW"
    elif result["co_owner_consent_required"] or result["missing_documents"]:
        stance, severity, action = "NEED_DATA", "MEDIUM", "REQUEST_CO_OWNER_CONSENT"
    else:
        stance, severity, action = "SUPPORT", "LOW", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Collateral & Legal Agent. Bạn CHỈ diễn giải kết quả kiểm tra sở hữu/thế chấp "
            "đã tra cứu từ hệ thống đăng ký — không tự suy đoán tình trạng pháp lý ngoài dữ liệu."
        ),
        user=(
            f"Kết quả validate_ownership: ownership_verified={result['ownership_verified']}, "
            f"encumbrance_found={result['encumbrance_found']}, "
            f"co_owner_consent_required={result['co_owner_consent_required']}, "
            f"missing_documents={result['missing_documents']}, legal_gap={result['legal_gap']}. "
            f"Viết 1-2 câu claim tiếng Việt nêu rõ tài sản có đủ điều kiện pháp lý để nhận thế "
            f"chấp hay cần xử lý gì trước."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="COLLATERAL_OWNERSHIP",
        claim_type="FACT",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=result["_evidence_ids"],
        confidence=result["confidence_score"] / 100,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding)


async def run_legal_checklist_check(case_id: str, as_of_date: str) -> FindingOut:
    """search_legal_checklist, enriched: semantic hits from Qdrant (citation
    text/score) joined with legal_checklist_template/regulatory_reference/
    checklist_completion (structured is_mandatory/status/legal_reference —
    common.py::read_checklist_items_sync) by checklist_id. Writes issue_key
    COLLATERAL_LEGAL_CHECKLIST — a missing MANDATORY item blocks
    disbursement regardless of how good coverage/ownership look."""
    client = _mcp_client()
    tools = {t.name: t for t in await client.get_tools()}

    semantic_hits = unwrap_mcp_result(
        await tools["search_legal_checklist"].ainvoke(
            {"collateral_type": COLLATERAL_TYPE, "query": "điều kiện pháp lý bắt buộc trước khi giải ngân", "top_k": 5}
        )
    )["results"]
    structured_items = await run_sync(read_checklist_items_sync, case_id, COLLATERAL_TYPE)
    structured_by_id = {item["checklist_id"]: item for item in structured_items}

    citations: list[Citation] = []
    checklist_items: list[dict] = []
    for hit in semantic_hits:
        checklist_id = hit.get("checklist_id")
        structured = structured_by_id.get(checklist_id) if checklist_id else None
        citations.append(
            Citation(
                source_type="LEGAL_CHECKLIST",
                source_id=COLLATERAL_TYPE,
                version=str(hit.get("version")) if hit.get("version") is not None else None,
                text=hit["text"],
                score=hit["score"],
            )
        )
        checklist_items.append(
            {
                "checklist_id": checklist_id,
                "required_document": structured["required_document"] if structured else hit["text"][:60],
                "is_mandatory": structured["is_mandatory"] if structured else hit.get("is_mandatory", True),
                "status": structured["status"] if structured else "missing",
                "legal_reference": structured["legal_reference"] if structured else None,
                "completion_id": structured["completion_id"] if structured else None,
            }
        )

    missing_mandatory = [item for item in checklist_items if item["is_mandatory"] and item["status"] != "completed"]
    condition_precedent = [item["required_document"] for item in missing_mandatory]
    grounded_evidence_ids = [item["completion_id"] for item in checklist_items if item["completion_id"]]

    if missing_mandatory:
        stance = "OPPOSE" if len(missing_mandatory) >= 2 else "CAUTION"
        severity = "HIGH" if grounded_evidence_ids else "MEDIUM"
        action = "COMPLETE_LEGAL_CHECKLIST"
    else:
        stance, severity, action = "SUPPORT", "LOW", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Collateral & Legal Agent. Bạn CHỈ liệt kê lại tình trạng checklist đã tra cứu "
            "(mục nào bắt buộc, mục nào còn thiếu) — không tự thêm điều kiện ngoài checklist."
        ),
        user=(
            f"Checklist pháp lý cho loại TSBĐ '{COLLATERAL_TYPE}': {checklist_items}. "
            f"Điều kiện tiên quyết còn thiếu: {condition_precedent or 'không có'}. "
            f"Viết 1-2 câu claim tiếng Việt tóm tắt tình trạng hoàn thiện hồ sơ pháp lý."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="COLLATERAL_LEGAL_CHECKLIST",
        claim_type="FACT",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=grounded_evidence_ids,
        citations=citations,
        confidence=0.9,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding)
