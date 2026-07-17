"""Policy & Compliance Agent — ai-architecture.md §5.3.

Tool allowlist: mcp-rag ONLY, for this Phase 3 scope (evaluate_policy_rules
and the KYC/AML mcp-external calls are deferred). This agent has no
mcp-deterministic client either — it never computes a ratio, only cites
policy text (ai-architecture.md §5.3 guardrail: "Chỉ trích dẫn văn bản
đúng phiên bản hiệu lực. Không tự tạo ngoại lệ.").

Every citation carries policy_id + version + effective_date + section —
if search_policy returns nothing usable, the guardrail is to say
INSUFFICIENT_EVIDENCE, never invent a rule (not yet implemented: this
Phase 3 pass assumes at least one hit, since the seed data guarantees it
for C06's known scenario).

DB access goes through common.run_sync(...) — see the comment on that
function for the deadlock this avoids under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import read_extracted_fields_sync, run_sync, unwrap_mcp_result, write_finding_sync
from app.config import MCP_RAG_URL
from app.llm.adapter import complete
from shared.schemas import Citation, FindingIn, FindingOut

AGENT_ID = "policy_compliance"
ISSUE_KEY = "REVENUE_RECONCILIATION"
PRODUCT_TYPE = "SME_WC"

# Matches the seeded REV-RECON v2.0 clause's own wording ("từ 5% trở lên") —
# NOT an SHB policy threshold, this IS the mock policy text itself.
_MISMATCH_NEEDS_EXPLANATION_PCT = 5.0


async def run_policy_agent(case_id: str, as_of_date: str) -> FindingOut:
    fields = await run_sync(read_extracted_fields_sync, case_id)
    revenue_bctc = fields["revenue_2025"]["value"]["amount_vnd"]
    revenue_tax = fields["revenue_2025_tax_filing"]["value"]["amount_vnd"]
    mismatch_pct = round(abs(revenue_bctc - revenue_tax) / revenue_bctc * 100, 1)

    client = MultiServerMCPClient({"rag": {"url": MCP_RAG_URL, "transport": "streamable_http"}})
    tools = {t.name: t for t in await client.get_tools()}

    search_result = unwrap_mcp_result(
        await tools["search_policy"].ainvoke(
            {
                "query": "doanh thu báo cáo tài chính và tờ khai thuế có chênh lệch thì xử lý thế nào",
                "product_type": PRODUCT_TYPE,
                "as_of_date": as_of_date,
                "top_k": 1,
            }
        )
    )
    top = search_result["results"][0]
    policy_citation = f"{top['policy_id']} v{top['version']} ({top['section']}, hiệu lực {top['effective_date']})"
    citation = Citation(
        source_type="POLICY",
        source_id=top["policy_id"],
        version=str(top["version"]),
        section=top.get("section"),
        effective_date=top["effective_date"],
        text=top["text"],
        score=top["score"],
    )

    needs_explanation = mismatch_pct >= _MISMATCH_NEEDS_EXPLANATION_PCT
    stance = "NEED_DATA" if needs_explanation else "SUPPORT"

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Policy & Compliance Agent. Bạn CHỈ được trích dẫn đúng chính sách đã "
            "tìm được qua công cụ tra cứu — không được tự suy diễn quy định khác hoặc tạo "
            "ngoại lệ không có trong văn bản."
        ),
        user=(
            f"Doanh thu giữa BCTC và tờ khai thuế lệch {mismatch_pct}%. "
            f"Chính sách áp dụng: {policy_citation} — nội dung: \"{top['text']}\". "
            f"Viết 1-2 câu claim tiếng Việt nêu rõ hồ sơ có cần giải trình bổ sung hay không, "
            f"dựa đúng theo nội dung chính sách trên."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY,
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity="HIGH" if needs_explanation else "LOW",
        evidence_ids=[fields["revenue_2025"]["evidence_id"], fields["revenue_2025_tax_filing"]["evidence_id"]],
        citations=[citation],
        confidence=0.9,
        recommended_action="REQUEST_EXPLANATION" if needs_explanation else None,
    )
    return await run_sync(
        write_finding_sync,
        finding,
        versions={"policy_id": top["policy_id"], "policy_version": top["version"]},
    )
