"""Financial Analysis Agent — ai-architecture.md §5.2.

Tool allowlist: mcp-deterministic ONLY (ai-architecture.md §6.1 — Financial
Agent has no way to reach mcp-rag/search_policy, even in principle, because
its MultiServerMCPClient is never configured with that server's URL).

Guardrail this file exists to prove: **the LLM never computes the ratio.**
`calculate_financial_ratios`/`calculate_coverage` (pure functions behind
mcp-deterministic) produce the numbers; the LLM only phrases claims
describing numbers it was handed, and it is never asked to "compute" or
"estimate" anything.

Writes TWO findings:
  - REPAYMENT_CAPACITY (DSCR-based, Phase 2)
  - COLLATERAL_COVERAGE (Phase 3) — a NAIVE coverage check using the
    document's own declared valuation, no expiry/independent-source check.
    Collateral Agent (collateral.py) checks the SAME issue_key more
    rigorously (official valuation + expiry rule) and can land on a
    different stance — this is intentional, it's what gives Phase 4's
    conflict detector real material to work with.

Every DB read/write goes through common.run_sync(...) — see the long
comment on that function for why a plain `with get_session()` block that
spans multiple `await`s deadlocked under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import read_extracted_fields_sync, read_requested_facility_sync, run_sync, unwrap_mcp_result, write_finding_sync
from app.config import MCP_DETERMINISTIC_URL
from app.llm.adapter import complete
from shared.schemas import FindingIn, FindingOut

AGENT_ID = "financial_analysis"

# DSCR ≥ 1.3 read as adequate repayment capacity for this mock scorecard —
# NOT an SHB policy threshold, just a demo-consistent cutoff (see the
# "mock ground truth" disclaimer in ai-architecture.md §10).
_DSCR_SUPPORT_THRESHOLD = 1.3
# Naive coverage ≥ 1.0 read as "collateral covers the facility" — Financial
# Agent's rough check; Collateral Agent applies more scrutiny separately.
_COVERAGE_SUPPORT_THRESHOLD = 1.0


def _mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient({"deterministic": {"url": MCP_DETERMINISTIC_URL, "transport": "streamable_http"}})


async def _repayment_capacity_finding(case_id: str, tools: dict, fields: dict) -> FindingOut:
    revenue = fields["revenue_2025"]["value"]["amount_vnd"]
    ebitda = fields["ebitda_2025"]["value"]["amount_vnd"]
    debt_service = fields["debt_service_annual"]["value"]["amount_vnd"]
    evidence_ids = [
        fields["revenue_2025"]["evidence_id"],
        fields["ebitda_2025"]["evidence_id"],
        fields["debt_service_annual"]["evidence_id"],
    ]

    ratios = unwrap_mcp_result(
        await tools["calculate_financial_ratios"].ainvoke(
            {"revenue": revenue, "ebitda": ebitda, "debt_service_annual": debt_service}
        )
    )
    dscr = ratios["outputs"]["dscr"]
    ebitda_margin = ratios["outputs"]["ebitda_margin"]
    formula_version = ratios["formula_version"]

    stance = "SUPPORT" if dscr >= _DSCR_SUPPORT_THRESHOLD else "CAUTION"
    severity = "MEDIUM" if stance == "SUPPORT" else "HIGH"

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Financial Analysis Agent trong hệ thống thẩm định tín dụng SME. "
            "Bạn CHỈ diễn giải các con số đã được tính sẵn bằng công cụ xác định — "
            "không được tự tính toán lại hay suy đoán số liệu khác."
        ),
        user=(
            f"DSCR đã tính: {dscr} (formula_version={formula_version}). "
            f"EBITDA margin: {ebitda_margin}. "
            f"Hãy viết 1-2 câu claim ngắn gọn bằng tiếng Việt mô tả khả năng trả nợ "
            f"dựa trên DSCR này, không thêm số liệu nào khác."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="REPAYMENT_CAPACITY",
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=evidence_ids,
        metrics={"dscr": dscr, "ebitda_margin": ebitda_margin},
        confidence=0.9 if stance == "SUPPORT" else 0.7,
        recommended_action=None,
    )
    return await run_sync(write_finding_sync, finding, versions={"formula_version": formula_version})


async def _collateral_coverage_finding(case_id: str, tools: dict, fields: dict, requested_facility: dict) -> FindingOut:
    requested_amount = requested_facility["amount_vnd"]
    valuation_amount = fields["valuation_amount"]["value"]["amount_vnd"]
    evidence_ids = [fields["valuation_amount"]["evidence_id"]]

    coverage = unwrap_mcp_result(
        await tools["calculate_coverage"].ainvoke(
            {"eligible_value": valuation_amount, "requested_amount": requested_amount}
        )
    )
    coverage_ratio = coverage["outputs"]["coverage_ratio"]
    formula_version = coverage["formula_version"]

    stance = "SUPPORT" if coverage_ratio >= _COVERAGE_SUPPORT_THRESHOLD else "CAUTION"

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Financial Analysis Agent. Bạn CHỈ diễn giải tỷ lệ coverage đã được "
            "tính sẵn, dựa trên giá trị định giá do khách hàng cung cấp — không tự kiểm "
            "tra tính pháp lý hay thời hạn của chứng thư định giá (việc đó thuộc về "
            "Collateral & Legal Agent)."
        ),
        user=(
            f"Coverage ratio đã tính: {coverage_ratio} (giá trị định giá / hạn mức đề nghị, "
            f"formula_version={formula_version}). Viết 1 câu claim ngắn gọn bằng tiếng Việt."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="COLLATERAL_COVERAGE",
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity="MEDIUM",
        evidence_ids=evidence_ids,
        metrics={"coverage_ratio": coverage_ratio},
        confidence=0.85,
        recommended_action=None,
    )
    return await run_sync(write_finding_sync, finding, versions={"formula_version": formula_version})


async def run_financial_agent(case_id: str) -> list[FindingOut]:
    fields = await run_sync(read_extracted_fields_sync, case_id)
    requested_facility = await run_sync(read_requested_facility_sync, case_id)
    client = _mcp_client()
    tools = {t.name: t for t in await client.get_tools()}

    return [
        await _repayment_capacity_finding(case_id, tools, fields),
        await _collateral_coverage_finding(case_id, tools, fields, requested_facility),
    ]
