"""Customer 360 & Credit History Agent — ai-architecture.md §5.5.
Logical role matches ai-architecture_v2.md §7.3's "Credit Conduct /
Customer 360" workcell (docs/architecture/ai-architecture_v2.md) — this
implementation stays a plain LangGraph fan-out node writing `FindingOut`
(v1 shape), per the reconciliation spec's "Lựa chọn B": adopt v2's
vocabulary (issue_key naming) now, defer the ExpertResult/AgentWorkItem
wrapper to a later slice.

Tool allowlist: mcp-external (`get_credit_obligations`, `query_cic_mock`)
+ mcp-deterministic (`calculate_cashflow_metrics`) — a FOURTH distinct
combination from Financial/Policy/Collateral, same "different tools,
different diligence" principle (data-flow.md §11).

Writes FOUR findings:
  - issue_key `CREDIT_CONDUCT` — TWO findings on this same issue_key:
    `run_customer_relationship_check` (get_customer_360, direct Postgres
    read + get_credit_obligations) and `run_cic_check` (query_cic_mock,
    external CIC snapshot). Grouped under one issue_key per
    ai-architecture_v2.md §12's vocabulary — matches the pattern Financial/
    Collateral already use on COLLATERAL_COVERAGE (two agents, one topic).
  - issue_key `CASHFLOW_QUALITY` — `run_cashflow_check`, reading
    cashflow_statement_summary (SHB transaction-based). Financial Agent
    ALSO writes to this issue_key from BCTC-reported cashflow
    (worker/app/agents/financial.py::_cashflow_quality_finding) — the two
    independent sources are meant to disagree when the customer's reported
    numbers don't match what actually moved through SHB accounts.
  - issue_key `RELATED_PARTY_CONCENTRATION` — `run_related_parties_check`.
    Deliberately NOT named `INDUSTRY_CONCENTRATION` (v2's vocab example) —
    that key belongs to the Business/Industry role (ngành/nhà cung cấp),
    a different concern from related-party/group-customer concentration
    under NHNN's rules.

Guardrail from ai-architecture.md §5.5 (reason golden case C05 exists):
identity_match_score below threshold must NEVER be treated as a confirmed
match — `run_cic_check` forces NEED_DATA regardless of debt_group/overdue
history when this fires.

DB access goes through common.run_sync(...) — see the long comment on that
function for the deadlock this avoids under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import (
    get_customer_360_sync,
    map_related_parties_sync,
    read_case_customer_id_sync,
    read_cashflow_summary_sync,
    read_extracted_fields_sync,
    run_sync,
    unwrap_mcp_result,
    write_finding_sync,
)
from app.config import MCP_DETERMINISTIC_URL, MCP_EXTERNAL_URL
from app.llm.adapter import complete
from shared.schemas import FindingIn, FindingOut

AGENT_ID = "customer_360"
ISSUE_KEY_CREDIT_CONDUCT = "CREDIT_CONDUCT"
ISSUE_KEY_CASHFLOW_QUALITY = "CASHFLOW_QUALITY"
ISSUE_KEY_RELATED_PARTY = "RELATED_PARTY_CONCENTRATION"

# Below this, identity is NOT confirmed — never merge CIC debt/overdue
# history onto this customer based on a partial name/tax-code match.
_IDENTITY_MATCH_THRESHOLD = 90.0
_HIGH_UTILIZATION_THRESHOLD = 0.9


def _mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "external": {"url": MCP_EXTERNAL_URL, "transport": "streamable_http"},
            "deterministic": {"url": MCP_DETERMINISTIC_URL, "transport": "streamable_http"},
        }
    )


async def run_customer_relationship_check(case_id: str, tools: dict) -> FindingOut:
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    profile = await run_sync(get_customer_360_sync, customer_id)
    obligations = unwrap_mcp_result(await tools["get_credit_obligations"].ainvoke({"customer_id": customer_id}))
    total_outstanding = obligations["total_obligation_vnd"]
    utilization_ratio = (
        round(total_outstanding / profile["total_credit_limit"], 3) if profile["total_credit_limit"] else None
    )

    if not profile["master_found"]:
        stance, severity, action = "NEED_DATA", "MEDIUM", "REQUEST_CUSTOMER_MASTER_DATA"
    elif utilization_ratio is not None and utilization_ratio > _HIGH_UTILIZATION_THRESHOLD:
        stance, severity, action = "CAUTION", "MEDIUM", "REVIEW_CREDIT_LIMIT_UTILIZATION"
    else:
        stance, severity, action = "SUPPORT", "LOW", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Customer 360 & Credit History Agent. Bạn CHỈ diễn giải hồ sơ quan hệ tín "
            "dụng đã tra cứu (hạn mức, dư nợ, thời gian quan hệ) — không tự suy đoán thông tin "
            "ngoài dữ liệu."
        ),
        user=(
            f"Tổng hạn mức đã cấp: {profile['total_credit_limit']}. Tổng dư nợ hiện tại: {total_outstanding}. "
            f"Tỷ lệ sử dụng hạn mức: {utilization_ratio}. Thời gian quan hệ: {profile['relationship_years']} năm. "
            f"Sản phẩm đã dùng: {profile['products_used']}. "
            f"Viết 1-2 câu claim tiếng Việt tóm tắt quan hệ tín dụng của khách hàng tại SHB."
        ),
    )

    metrics = {
        k: v
        for k, v in {
            "total_credit_limit": profile["total_credit_limit"],
            "total_outstanding_vnd": float(total_outstanding),
            "limit_utilization_ratio": utilization_ratio,
            "relationship_years": profile["relationship_years"],
        }.items()
        if v is not None
    }

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY_CREDIT_CONDUCT,
        claim_type="FACT",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=profile["_evidence_ids"],
        metrics=metrics,
        confidence=0.9,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding)


async def run_cic_check(case_id: str, tools: dict) -> FindingOut:
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    cic = unwrap_mcp_result(await tools["query_cic_mock"].ainvoke({"customer_id": customer_id}))
    identity_match_score = cic["identity_match_score"]
    debt_group = cic["cic_debt_group"]
    overdue_events = cic["overdue_events"]

    if identity_match_score < _IDENTITY_MATCH_THRESHOLD:
        # Guardrail (§5.5): never treat a low-confidence identity match as
        # this customer's own record — no debt_group/overdue conclusion at
        # all, regardless of what the (possibly wrong) snapshot says.
        stance, severity, action = "NEED_DATA", "HIGH", "MANUAL_IDENTITY_REVIEW"
    elif debt_group >= 3:
        stance, severity, action = "OPPOSE", "CRITICAL", "ESCALATE_CREDIT_RISK"
    elif overdue_events:
        stance, severity, action = "CAUTION", "MEDIUM", "REVIEW_OVERDUE_HISTORY"
    else:
        stance, severity, action = "SUPPORT", "LOW", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Customer 360 & Credit History Agent. Bạn CHỈ diễn giải kết quả tra cứu CIC "
            "đã có — nếu identity_match_score thấp, PHẢI nêu rõ đây là 'potential match' cần "
            "chuyên viên xác minh, KHÔNG được kết luận đây là cùng một khách hàng."
        ),
        user=(
            f"CIC debt_group={debt_group}, identity_match_score={identity_match_score}, "
            f"overdue_events={overdue_events}, tổng dư nợ tại TCTD khác={cic['total_outstanding_other_ctcd']}. "
            f"Viết 1-2 câu claim tiếng Việt."
        ),
    )

    # CIC snapshot has no local evidence row (external system, not an
    # ExtractedField/registry row) — cite the snapshot itself, same loose-
    # pointer convention collateral.py::run_ownership_check uses for
    # collateral_registry (a case/collateral-id string, not a UUID).
    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY_CREDIT_CONDUCT,
        claim_type="FACT",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=[f"cic:{customer_id}:{cic['report_date']}"],
        metrics={
            "cic_debt_group": float(debt_group),
            "identity_match_score": float(identity_match_score),
            "overdue_event_count": float(len(overdue_events)),
        },
        confidence=identity_match_score / 100,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding)


async def run_cashflow_check(case_id: str, tools: dict) -> FindingOut:
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    summary = await run_sync(read_cashflow_summary_sync, customer_id)

    if summary is None:
        finding = FindingIn(
            case_id=case_id,
            agent_id=AGENT_ID,
            issue_key=ISSUE_KEY_CASHFLOW_QUALITY,
            claim_type="FACT",
            claim="Chưa có dữ liệu dòng tiền qua tài khoản SHB (cashflow_statement_summary) cho khách hàng này.",
            stance="NEED_DATA",
            severity="MEDIUM",
            evidence_ids=[],
            confidence=1.0,
            recommended_action="REQUEST_ACCOUNT_ACTIVITY",
        )
        return await run_sync(write_finding_sync, finding)

    fields = await run_sync(read_extracted_fields_sync, case_id)
    net_revenue_entry = fields.get("net_revenue")
    net_revenue = net_revenue_entry["value"]["amount_vnd"] if net_revenue_entry else None

    profile = await run_sync(get_customer_360_sync, customer_id)
    # Approximation for "tổng ghi Có tài khoản trong kỳ" — the raw
    # account_transaction ledger was deferred (plan's Rủi ro note); summed
    # avg_balance across accounts stands in for account activity level.
    # Documented here, not hidden, so a later pass knows exactly what to
    # replace once real posting-level data exists.
    account_credit_turnover = profile["total_avg_balance"]

    metrics_result = unwrap_mcp_result(
        await tools["calculate_cashflow_metrics"].ainvoke(
            {
                "cf_operating": summary["cf_operating"] or 0.0,
                "cf_investing": summary["cf_investing"] or 0.0,
                "cf_financing": summary["cf_financing"] or 0.0,
                "account_credit_turnover": account_credit_turnover,
                "net_revenue": net_revenue or 0.0,
            }
        )
    )
    net_cashflow = metrics_result["outputs"]["net_cashflow"]
    operating_cf_ratio = metrics_result["outputs"]["operating_cf_ratio"]
    formula_version = metrics_result["formula_version"]

    if net_cashflow < 0 and (summary["cf_financing"] or 0) > 0:
        # HĐKD âm được bù bằng vay/phát hành mới — cảnh báo rủi ro thanh
        # khoản, đúng logic cẩm nang (Kết luận bắt buộc mục 4, Phần C).
        stance, severity, action = "OPPOSE", "HIGH", "REVIEW_LIQUIDITY_RISK"
    elif net_cashflow < 0:
        stance, severity, action = "CAUTION", "MEDIUM", "REVIEW_CASHFLOW"
    else:
        stance, severity, action = "SUPPORT", "MEDIUM", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Customer 360 & Credit History Agent. Bạn CHỈ diễn giải dòng tiền qua tài "
            "khoản SHB đã tính — đây là dữ liệu giao dịch THẬT, độc lập với BCTC khách tự nộp "
            "(do Financial Agent phân tích riêng). Không tự đối chiếu hay kết luận thay Financial Agent."
        ),
        user=(
            f"Dòng tiền qua tài khoản SHB kỳ {summary['period']}: cf_operating={summary['cf_operating']}, "
            f"cf_investing={summary['cf_investing']}, cf_financing={summary['cf_financing']}, "
            f"net_cashflow={net_cashflow}, operating_cf_ratio={operating_cf_ratio}. "
            f"Viết 1-2 câu claim tiếng Việt mô tả chất lượng dòng tiền thực qua tài khoản."
        ),
    )

    metrics = {
        k: v
        for k, v in {"net_cashflow": net_cashflow, "operating_cf_ratio": operating_cf_ratio}.items()
        if v is not None
    }

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY_CASHFLOW_QUALITY,
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=[summary["id"]],
        metrics=metrics,
        confidence=0.85,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding, versions={"formula_version": formula_version})


async def run_related_parties_check(case_id: str, tools: dict) -> FindingOut:
    customer_id = await run_sync(read_case_customer_id_sync, case_id)
    graph = await run_sync(map_related_parties_sync, customer_id)
    related_parties = graph["related_parties"]

    if not related_parties:
        group_total_exposure = 0.0
        concentration_ratio = 0.0
    else:
        own_obligations = unwrap_mcp_result(await tools["get_credit_obligations"].ainvoke({"customer_id": customer_id}))
        group_total_exposure = own_obligations["total_obligation_vnd"]
        for rp in related_parties:
            try:
                rp_obligations = unwrap_mcp_result(
                    await tools["get_credit_obligations"].ainvoke({"customer_id": rp["id"]})
                )
                group_total_exposure += rp_obligations["total_obligation_vnd"]
            except Exception:  # noqa: BLE001 — related party not in mock registry, skip rather than fabricate
                continue
        concentration_ratio = (
            round(group_total_exposure / own_obligations["total_obligation_vnd"], 3)
            if own_obligations["total_obligation_vnd"]
            else None
        )

    has_cross_guarantee = graph["cross_guarantee_total"] > 0
    if has_cross_guarantee or len(related_parties) >= 2:
        stance, severity, action = "CAUTION", "MEDIUM", "REVIEW_RELATED_PARTY_EXPOSURE"
    else:
        stance, severity, action = "SUPPORT", "LOW", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Customer 360 & Credit History Agent. Bạn CHỈ diễn giải đồ thị bên liên quan "
            "đã tra cứu (cổ đông, người đại diện, nhóm khách hàng liên quan theo quy định NHNN) "
            "— không tự suy đoán quan hệ ngoài dữ liệu."
        ),
        user=(
            f"Cổ đông: {graph['shareholders']}. Người đại diện: {graph['legal_representatives']}. "
            f"Bên liên quan: {related_parties}. Tổng bảo lãnh chéo: {graph['cross_guarantee_total']}. "
            f"Tổng dư nợ nhóm liên quan (ước tính): {group_total_exposure}. "
            f"Viết 1-2 câu claim tiếng Việt về mức độ tập trung rủi ro nhóm liên quan."
        ),
    )

    metrics = {
        k: v
        for k, v in {
            "group_total_exposure_vnd": group_total_exposure,
            "concentration_ratio": concentration_ratio,
            "cross_guarantee_total_vnd": graph["cross_guarantee_total"],
        }.items()
        if v is not None
    }

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=ISSUE_KEY_RELATED_PARTY,
        claim_type="FACT",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=graph["_evidence_ids"],
        metrics=metrics,
        confidence=0.85,
        recommended_action=action,
    )
    return await run_sync(write_finding_sync, finding)


async def run_customer360_agent(case_id: str) -> list[FindingOut]:
    client = _mcp_client()
    tools = {t.name: t for t in await client.get_tools()}

    return [
        await run_customer_relationship_check(case_id, tools),
        await run_cic_check(case_id, tools),
        await run_cashflow_check(case_id, tools),
        await run_related_parties_check(case_id, tools),
    ]
