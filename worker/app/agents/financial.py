"""Financial Analysis Agent — ai-architecture.md §5.2.

Tool allowlist: mcp-deterministic ONLY (ai-architecture.md §6.1 — Financial
Agent has no way to reach mcp-rag/search_policy, even in principle, because
its MultiServerMCPClient is never configured with that server's URL).

Guardrail this file exists to prove: **the LLM never computes the ratio.**
`calculate_financial_ratios`/`calculate_coverage` (pure functions behind
mcp-deterministic) produce the numbers; the LLM only phrases claims
describing numbers it was handed, and it is never asked to "compute" or
"estimate" anything.

Writes SIX findings:
  - REPAYMENT_CAPACITY (DSCR-based, Phase 2)
  - COLLATERAL_COVERAGE (Phase 3) — a NAIVE coverage check using the
    document's own declared valuation, no expiry/independent-source check.
    Collateral Agent (collateral.py) checks the SAME issue_key more
    rigorously (official valuation + expiry rule) and can land on a
    different stance — this is intentional, it's what gives Phase 4's
    conflict detector real material to work with.
  - LIQUIDITY / PROFITABILITY / LEVERAGE / ACTIVITY — standard financial-
    statement ratio analysis (mcp-deterministic::calculate_statement_ratios),
    graded against shared/constants.py::INDUSTRY_AVG_RATIOS. Guarded by
    REQUIRED_STATEMENT_FIELDS: if the case's ExtractedField set is missing
    any field that analysis needs, this whole block is replaced by a single
    NEED_DATA finding instead of computing on incomplete data.

Every DB read/write goes through common.run_sync(...) — see the long
comment on that function for why a plain `with get_session()` block that
spans multiple `await`s deadlocked under LangGraph's parallel FanOut.
"""
from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.common import read_extracted_fields_sync, read_requested_facility_sync, run_sync, unwrap_mcp_result, write_finding_sync
from app.config import MCP_DETERMINISTIC_URL
from app.llm.adapter import complete
from shared.constants import INDUSTRY_AVG_RATIOS, REQUIRED_STATEMENT_FIELDS, STATEMENT_BENCHMARK_VERSION
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


# ---------------------------------------------------------------------------
# Standard financial-statement ratio analysis (LIQUIDITY / PROFITABILITY /
# LEVERAGE / ACTIVITY) — separate from the DSCR-based REPAYMENT_CAPACITY
# finding above, which stays as-is.
# ---------------------------------------------------------------------------

# Fields calculate_statement_ratios reads (mcp-deterministic/app/server.py).
# A superset of REQUIRED_STATEMENT_FIELDS — some of these are optional
# (e.g. long_term_debt/fixed_assets_and_ltd_investments only feed
# net_working_capital, avg_* only feed ACTIVITY) so a missing one degrades
# that one ratio to `grade: None` rather than blocking the whole finding;
# only a REQUIRED_STATEMENT_FIELDS gap blocks everything (see
# run_financial_agent below).
_STATEMENT_AMOUNT_FIELDS = [
    "cash_and_equivalents", "short_term_investments", "accounts_receivable", "inventory",
    "current_assets_total", "fixed_assets_and_ltd_investments", "total_assets",
    "current_liabilities", "long_term_debt", "total_liabilities", "total_equity",
    "total_capital_source", "net_revenue", "cogs", "net_profit_after_tax",
    "cf_operating", "cf_investing", "cf_financing",
    "avg_current_assets", "avg_accounts_receivable", "avg_inventory", "avg_total_assets",
]

# Which extracted fields ground each group's ratios — used to build
# evidence_ids per finding (NFR-01: a finding must cite what it used).
_GROUP_EVIDENCE_FIELDS = {
    "LIQUIDITY": ["cash_and_equivalents", "short_term_investments", "accounts_receivable", "inventory", "current_liabilities"],
    "PROFITABILITY": ["net_profit_after_tax", "total_assets", "total_equity"],
    "LEVERAGE": ["total_liabilities", "total_capital_source", "total_equity", "long_term_debt", "fixed_assets_and_ltd_investments"],
    "ACTIVITY": ["net_revenue", "avg_current_assets", "avg_accounts_receivable", "cogs", "avg_inventory", "avg_total_assets"],
}

# grade -> (stance, severity). `None` (couldn't be graded — a value or its
# industry_avg counterpart was missing) maps to NEED_DATA, not a fabricated
# stance. OPPOSE/HIGH is safe under NFR-01 here because a group only grades
# at all when its underlying fields (and thus evidence_ids) are present.
_STANCE_SEVERITY_BY_GRADE = {
    "Tot": ("SUPPORT", "LOW"),
    "Kha": ("SUPPORT", "MEDIUM"),
    "Trung binh": ("CAUTION", "MEDIUM"),
    "Kem": ("OPPOSE", "HIGH"),
    None: ("NEED_DATA", "MEDIUM"),
}

_GROUP_LABEL = {
    "LIQUIDITY": "khả năng thanh toán",
    "PROFITABILITY": "khả năng sinh lời",
    "LEVERAGE": "cân đối tài chính / đòn bẩy",
    "ACTIVITY": "khả năng hoạt động",
}


def _statement_field_value(fields: dict, key: str) -> float | None:
    entry = fields.get(key)
    if entry is None:
        return None
    value = entry["value"]
    return value.get("amount_vnd") if isinstance(value, dict) else value


def _missing_required_statement_fields(fields: dict) -> list[str]:
    return sorted(k for k in REQUIRED_STATEMENT_FIELDS if k not in fields)


async def _statement_need_data_finding(case_id: str, missing: list[str], fields: dict) -> FindingOut:
    """One NEED_DATA finding replacing the whole statement-ratio block when
    a required field is absent — per §5.2 guardrail, "thiếu trường cốt lõi
    → NEED_DATA, không nội suy." evidence_ids cites whichever required
    fields ARE present (proves the gap is real, not an agent glitch);
    severity can only be HIGH if at least one such field exists (NFR-01).

    evidence_ids is deliberately NEVER [] (see _fields_missing_finding
    below for the full explanation): graph/decision.py::
    _validate_evidence_chain — a stricter, severity-blind check than this
    module's own NFR-01 guard — rejects ANY DecisionPackage entry pointing
    at a finding with empty evidence_ids, crashing synthesis. Falls back
    to a synthetic pointer when NO required field is present at all."""
    present_evidence_ids = [fields[k]["evidence_id"] for k in REQUIRED_STATEMENT_FIELDS if k in fields]
    evidence_ids = present_evidence_ids or [f"missing-field:FINANCIAL_STATEMENT_ANALYSIS:{case_id}"]
    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="FINANCIAL_STATEMENT_ANALYSIS",
        claim_type="FACT",
        claim=(
            "Thiếu dữ liệu bắt buộc để phân tích BCTC chuẩn (thanh toán/sinh lời/đòn bẩy/hoạt động): "
            + ", ".join(missing)
            + ". Cần bổ sung trước khi tính các nhóm chỉ số này."
        ),
        stance="NEED_DATA",
        severity="HIGH" if present_evidence_ids else "MEDIUM",
        evidence_ids=evidence_ids,
        confidence=1.0,
        recommended_action="REQUEST_FINANCIALS",
    )
    return await run_sync(write_finding_sync, finding)


async def _statement_group_finding(
    case_id: str,
    *,
    group: str,
    grade: str | None,
    ratio_entries: dict,
    fields: dict,
    formula_version: str,
) -> FindingOut:
    """One finding for one ratio group (LIQUIDITY/PROFITABILITY/LEVERAGE/
    ACTIVITY). `ratio_entries` is that group's slice of
    calculate_statement_ratios' output (e.g. `outputs["liquidity"]`) — each
    value has a `"value"` key regardless of whether it's a graded ratio
    (`_ratio_entry`) or `net_working_capital` (value + sign only), so
    flattening into `metrics` works uniformly. `grade` is the group's
    already-computed group_rollup entry — this function grades nothing
    itself, only interprets."""
    stance, severity = _STANCE_SEVERITY_BY_GRADE[grade]
    metrics = {k: v["value"] for k, v in ratio_entries.items() if v.get("value") is not None}
    evidence_ids = [fields[k]["evidence_id"] for k in _GROUP_EVIDENCE_FIELDS[group] if k in fields]

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Financial Analysis Agent. Bạn CHỈ diễn giải grade đã được chấm sẵn "
            "(so với trung bình ngành) — không tự tính lại tỷ số hay tự chấm điểm khác."
        ),
        user=(
            f"Nhóm chỉ số '{_GROUP_LABEL[group]}' được chấm: {grade or 'không đủ dữ liệu để chấm'}. "
            f"Các chỉ số cụ thể: {metrics}. "
            f"Viết 1-2 câu claim tiếng Việt mô tả kết quả nhóm này so với trung bình ngành."
        ),
    )

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=group,
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=evidence_ids,
        metrics=metrics,
        confidence=0.85,
        recommended_action=None if stance == "SUPPORT" else "REVIEW_FINANCIAL_STATEMENTS",
    )
    return await run_sync(
        write_finding_sync, finding, versions={"formula_version": formula_version, "benchmark_version": STATEMENT_BENCHMARK_VERSION}
    )


async def _cashflow_quality_finding(case_id: str, tools: dict, fields: dict) -> FindingOut | None:
    """CASHFLOW_QUALITY — issue_key SHARED with Customer 360's
    run_cashflow_check (worker/app/agents/customer360.py). This version
    derives cf_operating/cf_investing/cf_financing from the CUSTOMER'S OWN
    submitted BCTC (extracted_fields); Customer 360's version reads
    cashflow_statement_summary (SHB transaction data) instead — two
    INDEPENDENT sources on purpose, so a real mismatch between "what the
    customer reported" and "what actually moved through SHB accounts"
    surfaces as a conflict (data-flow.md §5 pattern, same as
    COLLATERAL_COVERAGE between Financial and Collateral).

    Reuses calculate_cashflow_metrics (mcp-deterministic) — same tool
    Customer 360 calls — but ignores its account_turnover_vs_revenue output
    (account_credit_turnover=0.0 here on purpose): that metric only makes
    sense for the transaction-based source, not a BCTC read.

    Returns None (writes nothing) if cf_investing/cf_financing aren't in
    this case's extracted_fields yet (older/partial seed) — cf_operating
    alone isn't enough to compute net_cashflow, and this finding is
    additive, not required for run_financial_agent's other 6 findings."""
    cf_operating = _statement_field_value(fields, "cf_operating")
    cf_investing = _statement_field_value(fields, "cf_investing")
    cf_financing = _statement_field_value(fields, "cf_financing")
    if cf_operating is None or cf_investing is None or cf_financing is None:
        return None

    net_revenue = _statement_field_value(fields, "net_revenue")
    evidence_ids = [fields[k]["evidence_id"] for k in ("cf_operating", "cf_investing", "cf_financing") if k in fields]

    metrics_result = unwrap_mcp_result(
        await tools["calculate_cashflow_metrics"].ainvoke(
            {
                "cf_operating": cf_operating,
                "cf_investing": cf_investing,
                "cf_financing": cf_financing,
                "account_credit_turnover": 0.0,
                "net_revenue": net_revenue or 0.0,
            }
        )
    )
    net_cashflow = metrics_result["outputs"]["net_cashflow"]
    operating_cf_ratio = metrics_result["outputs"]["operating_cf_ratio"]
    formula_version = metrics_result["formula_version"]

    if net_cashflow < 0 and cf_financing > 0:
        stance, severity, recommended_action = "OPPOSE", "HIGH", "REVIEW_LIQUIDITY_RISK"
    elif net_cashflow < 0:
        stance, severity, recommended_action = "CAUTION", "MEDIUM", "REVIEW_CASHFLOW"
    else:
        stance, severity, recommended_action = "SUPPORT", "MEDIUM", None

    claim = await complete(
        tier="reasoning",
        system=(
            "Bạn là Financial Analysis Agent. Bạn CHỈ diễn giải dòng tiền đã tính từ BCTC khách "
            "nộp — đây là số liệu tự khai, độc lập với dữ liệu giao dịch thật qua SHB (do "
            "Customer 360 Agent phân tích riêng). Không tự đối chiếu hay kết luận thay agent khác."
        ),
        user=(
            f"Dòng tiền theo BCTC: cf_operating={cf_operating}, cf_investing={cf_investing}, "
            f"cf_financing={cf_financing}, net_cashflow={net_cashflow}, operating_cf_ratio={operating_cf_ratio}. "
            f"Viết 1-2 câu claim tiếng Việt mô tả chất lượng dòng tiền theo BCTC."
        ),
    )

    metrics = {k: v for k, v in {"net_cashflow": net_cashflow, "operating_cf_ratio": operating_cf_ratio}.items() if v is not None}

    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key="CASHFLOW_QUALITY",
        claim_type="INFERENCE",
        claim=claim,
        stance=stance,
        severity=severity,
        evidence_ids=evidence_ids,
        metrics=metrics,
        confidence=0.85,
        recommended_action=recommended_action,
    )
    return await run_sync(write_finding_sync, finding, versions={"formula_version": formula_version})


_REPAYMENT_CAPACITY_FIELDS = ["revenue_2025", "ebitda_2025", "debt_service_annual"]


async def _fields_missing_finding(case_id: str, *, issue_key: str, missing: list[str], fields: dict, required: list[str], context_label: str) -> FindingOut:
    """Written INSTEAD of {issue_key} when one of `required` is absent from
    extracted_fields — same guardrail as _statement_need_data_finding
    above, applied to the two findings (REPAYMENT_CAPACITY/
    COLLATERAL_COVERAGE) that used to read `fields[...]` directly and raise
    a bare KeyError on a gap. That KeyError propagated out of this agent
    entirely and _run_fanout_agent (graph/build.py) turned it into an
    opaque AGENT_UNAVAILABLE finding whose claim was just the raw field
    name (e.g. "'revenue_2025'") — a real gap in the customer's submitted
    data looked identical to a tool crash. This keeps the SAME issue_key
    so downstream conflict detection still has an entry to reason about,
    just with stance=NEED_DATA instead of a computed verdict.

    evidence_ids is deliberately NEVER [] (found the hard way, same as
    graph/build.py::_fallback_agent_unavailable_finding's docstring warns):
    when NONE of `required` are present, graph/decision.py::
    _validate_evidence_chain — a STRICTER, severity-blind check than
    shared/state.py::write_finding's own NFR-01 guard — rejects ANY
    DecisionPackage entry pointing at a finding with empty evidence_ids and
    crashes the whole synthesis step. Falls back to the same "pointer, not
    a UUID" convention customer360.py::run_cic_check uses for non-DB
    evidence when there's genuinely nothing local to cite."""
    present_evidence_ids = [fields[k]["evidence_id"] for k in required if k in fields]
    evidence_ids = present_evidence_ids or [f"missing-field:{issue_key}:{case_id}"]
    finding = FindingIn(
        case_id=case_id,
        agent_id=AGENT_ID,
        issue_key=issue_key,
        claim_type="FACT",
        claim=(
            f"Thiếu dữ liệu bắt buộc để {context_label}: " + ", ".join(missing) + ". Cần bổ sung trước khi tính."
        ),
        stance="NEED_DATA",
        severity="HIGH" if present_evidence_ids else "MEDIUM",
        evidence_ids=evidence_ids,
        confidence=1.0,
        recommended_action="REQUEST_FINANCIALS",
    )
    return await run_sync(write_finding_sync, finding)


async def _repayment_capacity_finding(case_id: str, tools: dict, fields: dict) -> FindingOut:
    missing = [k for k in _REPAYMENT_CAPACITY_FIELDS if k not in fields]
    if missing:
        return await _fields_missing_finding(
            case_id, issue_key="REPAYMENT_CAPACITY", missing=missing, fields=fields,
            required=_REPAYMENT_CAPACITY_FIELDS, context_label="tính khả năng trả nợ (DSCR)",
        )

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
    if "valuation_amount" not in fields:
        return await _fields_missing_finding(
            case_id, issue_key="COLLATERAL_COVERAGE", missing=["valuation_amount"], fields=fields,
            required=["valuation_amount"], context_label="tính tỷ lệ coverage tài sản bảo đảm",
        )

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

    findings = [
        await _repayment_capacity_finding(case_id, tools, fields),
        await _collateral_coverage_finding(case_id, tools, fields, requested_facility),
    ]

    missing = _missing_required_statement_fields(fields)
    if missing:
        # Guardrail (§5.2): a core field is absent -> NEED_DATA for the
        # whole statement-ratio block, no tool call, no interpolation.
        findings.append(await _statement_need_data_finding(case_id, missing, fields))
        return findings

    financials = {k: _statement_field_value(fields, k) for k in _STATEMENT_AMOUNT_FIELDS}
    statement = unwrap_mcp_result(
        await tools["calculate_statement_ratios"].ainvoke({"financials": financials, "industry_avg": INDUSTRY_AVG_RATIOS})
    )
    formula_version = statement["formula_version"]
    outputs = statement["outputs"]
    group_rollup = statement["group_rollup"]

    group_ratio_entries = {
        "LIQUIDITY": outputs["liquidity"],
        "PROFITABILITY": outputs["profitability"],
        "LEVERAGE": outputs["leverage"],
        "ACTIVITY": outputs["activity"],
    }
    for group in ("LIQUIDITY", "PROFITABILITY", "LEVERAGE", "ACTIVITY"):
        findings.append(
            await _statement_group_finding(
                case_id,
                group=group,
                grade=group_rollup[group],
                ratio_entries=group_ratio_entries[group],
                fields=fields,
                formula_version=formula_version,
            )
        )

    cashflow_finding = await _cashflow_quality_finding(case_id, tools, fields)
    if cashflow_finding is not None:
        findings.append(cashflow_finding)

    return findings
