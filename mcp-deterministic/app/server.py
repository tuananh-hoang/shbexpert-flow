"""mcp-deterministic — MCP server exposing pure Python calculation tools.

Allowlist (ai-architecture.md §6.1): Financial, Policy, Collateral agents
connect here. Nothing in this server calls an LLM — every tool is a plain
function with a fixed formula_version, so results are reproducible and
testable (PRD 12.1: 100% of mock calculations must match tolerance).

Phase 2 added `calculate_financial_ratios`; Phase 3 adds `calculate_coverage`
(shared by Financial + Collateral agents). `evaluate_policy_rules` is
deferred — Policy Agent's Phase 3 finding comes from search_policy alone.
"""
# NOTE: deliberately NO `from __future__ import annotations` here.
# mcp==1.12.4's FastMCP tool registration calls `issubclass(param.annotation,
# Context)` on every parameter without resolving PEP 563 stringized
# annotations first — with the future import, `param.annotation` is the
# literal string "float" instead of the `float` class, and issubclass()
# raises `TypeError: issubclass() arg 1 must be a class`. Any @mcp.tool()
# function with typed parameters breaks under that import; verified by
# reproducing the exact traceback with/without it. Keep this file free of
# the future import even though every other module in the repo uses it.
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

SERVER_NAME = "mcp-deterministic"
PORT = 8200

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def ping() -> dict:
    """Health-check tool — confirms the MCP connection works end to end.
    Not part of the real tool allowlist; safe to remove once Phase 2/3
    tools exist and an agent has exercised them at least once."""
    return {"status": "ok", "server": SERVER_NAME}


FORMULA_VERSION = "FIN-0.3-MOCK"


@mcp.tool()
def calculate_financial_ratios(revenue: float, ebitda: float, debt_service_annual: float) -> dict:
    """Pure Python financial ratio calculation — NO LLM involved (overview.md
    nguyên tắc 4: "Tính toán xác định"). The Financial Agent calls this with
    numbers read from ExtractedField rows; the LLM only explains the result
    afterward, never computes it. Every result carries formula_version so
    the eval harness can assert exact-match against a test vector
    (ai-architecture.md §6.3, PRD 12.1: 100% of mock calculations must match
    tolerance).

    Returns dscr (debt service coverage ratio) and ebitda_margin. Extend
    with more ratios (current_ratio, debt_ratio, ...) as later phases need
    them — keep every new ratio a plain formula, never a model call.
    """
    dscr = round(ebitda / debt_service_annual, 3) if debt_service_annual else None
    ebitda_margin = round(ebitda / revenue, 4) if revenue else None
    return {
        "outputs": {"dscr": dscr, "ebitda_margin": ebitda_margin},
        "inputs": {
            "revenue": revenue,
            "ebitda": ebitda,
            "debt_service_annual": debt_service_annual,
        },
        "formula_version": FORMULA_VERSION,
    }


COVERAGE_FORMULA_VERSION = "COL-0.2-MOCK"


@mcp.tool()
def calculate_coverage(eligible_value: float, requested_amount: float) -> dict:
    """Pure Python coverage-ratio calculation. Reused by BOTH Financial and
    Collateral agents (ai-architecture.md §6.1 lists this under the shared
    mcp-deterministic allowlist) — with different `eligible_value` inputs:
    Financial passes the document's face-value valuation (naive, no
    haircut/expiry check); Collateral passes a value it has itself vetted
    (e.g. after checking the certificate hasn't expired). Same formula,
    different diligence upstream — this is deliberate: it is what lets
    Phase 4's conflict detector find a real disagreement on
    issue_key=COLLATERAL_COVERAGE without needing two different formulas.
    """
    coverage_ratio = round(eligible_value / requested_amount, 3) if requested_amount else None
    return {
        "outputs": {"coverage_ratio": coverage_ratio},
        "inputs": {"eligible_value": eligible_value, "requested_amount": requested_amount},
        "formula_version": COVERAGE_FORMULA_VERSION,
    }


COLLATERAL_COVERAGE_FORMULA_VERSION = "COL-1.0"


@mcp.tool()
def calculate_collateral_coverage(eligible_value: float, haircut_rate: float, total_obligation: float) -> dict:
    """Full collateral-coverage calculation (Collateral & Legal Agent) —
    distinct from `calculate_coverage` above, which Financial Agent keeps
    calling unchanged with its original naive signature. Pure Python, no
    Postgres access (haircut_rate/total_obligation are looked up by the
    caller — collateral.py — via shared.db / tools-mock BEFORE calling this
    tool; see worker/app/agents/common.py::read_haircut_rate_sync).

    eligible_value: the collateral's value BEFORE haircut (typically
        forced_sale_value from get_valuation — the conservative choice).
    haircut_rate: fraction (0-1) from haircut_matrix for this collateral_type.
    total_obligation: dư nợ + dư bảo lãnh + dư L/C tại ngân hàng (tools-mock
        /credit-obligations/{customer_id}), NOT just the amount being
        requested now — matches Cẩm nang trang 25's "Tổng nghĩa vụ tại MB".

    coverage_tier thresholds: >=1.0 OVER_SECURED, >=0.7 ADEQUATE, else
    UNDER_SECURED — mirrors the Tốt/Khá/Kém banding style used elsewhere
    (calculate_statement_ratios) for consistency, though this is a 3-tier
    scale specific to collateral coverage, not the same bands.
    """
    adjusted_eligible_value = round(eligible_value * (1 - haircut_rate), 2)
    coverage_ratio = round(adjusted_eligible_value / total_obligation, 3) if total_obligation else None
    gap = round(adjusted_eligible_value - total_obligation, 2) if total_obligation else None

    if coverage_ratio is None:
        coverage_tier = None
    elif coverage_ratio >= 1.0:
        coverage_tier = "OVER_SECURED"
    elif coverage_ratio >= 0.7:
        coverage_tier = "ADEQUATE"
    else:
        coverage_tier = "UNDER_SECURED"

    return {
        "outputs": {
            "adjusted_eligible_value": adjusted_eligible_value,
            "coverage_ratio": coverage_ratio,
            "gap": gap,
            "coverage_tier": coverage_tier,
        },
        "inputs": {"eligible_value": eligible_value, "haircut_rate": haircut_rate, "total_obligation": total_obligation},
        "formula_version": COLLATERAL_COVERAGE_FORMULA_VERSION,
    }


STATEMENT_FORMULA_VERSION = "FIN-1.0"

# grade -> numeric rank, used only to find the WORST grade in a group
# (conservative rollup: one weak ratio is enough to flag the group for
# review, matching decision.py's overall "don't average away a real gap"
# posture — see _check_hard_gates's docstring in worker/app/graph/decision.py).
_GRADE_RANK = {"Kem": 0, "Trung binh": 1, "Kha": 2, "Tot": 3}
_GRADE_BY_RANK = {v: k for k, v in _GRADE_RANK.items()}


def grade_vs_benchmark(value, industry_avg, *, lower_is_better: bool = False):
    """Grades one ratio against its industry average — the same
    Tốt/Khá/Trung bình/Kém bands used throughout standard financial-
    statement analysis: ratio_vs_avg >= 1.2 -> Tot, >= 1.0 -> Kha,
    >= 0.7 -> Trung binh, else -> Kem.

    `lower_is_better=True` inverts the ratio first (e.g. debt_ratio: a
    company BELOW the industry average is the good outcome), so the same
    four bands always mean "better than peers" -> worse, consistently.
    Returns None (no grade) when value or industry_avg is missing/zero —
    caller must treat that as ungraded, not as "Kem".
    """
    if value is None or not industry_avg:
        return None, None
    ratio_vs_avg = round((industry_avg / value if lower_is_better else value / industry_avg), 3)
    if ratio_vs_avg >= 1.2:
        grade = "Tot"
    elif ratio_vs_avg >= 1.0:
        grade = "Kha"
    elif ratio_vs_avg >= 0.7:
        grade = "Trung binh"
    else:
        grade = "Kem"
    return ratio_vs_avg, grade


def _ratio_entry(value, industry_avg, *, lower_is_better: bool = False) -> dict:
    ratio_vs_avg, grade = grade_vs_benchmark(value, industry_avg, lower_is_better=lower_is_better)
    return {"value": value, "industry_avg": industry_avg, "ratio_vs_avg": ratio_vs_avg, "grade": grade}


def _worst_grade(entries: list[dict]) -> str | None:
    ranks = [_GRADE_RANK[e["grade"]] for e in entries if e.get("grade") is not None]
    return _GRADE_BY_RANK[min(ranks)] if ranks else None


def _safe_div(numerator, denominator):
    if numerator is None or denominator is None or not denominator:
        return None
    return round(numerator / denominator, 4)


@mcp.tool()
def calculate_statement_ratios(financials: dict, industry_avg: dict) -> dict:
    """Standard financial-statement ratio analysis — thuần Python, không
    LLM (overview.md nguyên tắc 4). Financial Agent gọi tool này SAU khi đã
    tự kiểm REQUIRED_STATEMENT_FIELDS (shared/constants.py); mọi field
    thiếu ở đây chỉ khiến RIÊNG chỉ số phụ thuộc nó bị bỏ qua (None), không
    làm sập cả tool — an toàn nếu agent gọi với dữ liệu chưa đầy đủ tuyệt đối.

    `financials`: dict các trường BCTC chuẩn (balance sheet, income
    statement, cashflow statement, bình quân kỳ — xem
    shared/constants.py::REQUIRED_STATEMENT_FIELDS cho nhóm bắt buộc).
    `industry_avg`: dict trung bình ngành cho từng chỉ số (xem
    shared/constants.py::INDUSTRY_AVG_RATIOS) — dùng để chấm Tốt/Khá/Trung
    bình/Kém, KHÔNG phải một tỷ lệ SHB hay ngân hàng cụ thể nào quy định.

    Trả về ratio_table theo 4 nhóm (liquidity/profitability/leverage/
    activity) + group_rollup (grade tệ nhất mỗi nhóm) + count_tot_kha (đếm
    số nhóm đạt Tốt/Khá, tối đa 4) — Financial Agent dùng count_tot_kha để
    suy stance cho mỗi finding, KHÔNG tự đếm lại bằng LLM.
    """
    f = financials
    avg = industry_avg

    current_ratio = _safe_div(
        (f.get("cash_and_equivalents") or 0)
        + (f.get("short_term_investments") or 0)
        + (f.get("accounts_receivable") or 0)
        + (f.get("inventory") or 0),
        f.get("current_liabilities"),
    )
    quick_ratio = _safe_div(
        (f.get("cash_and_equivalents") or 0) + (f.get("short_term_investments") or 0) + (f.get("accounts_receivable") or 0),
        f.get("current_liabilities"),
    )
    cash_ratio = _safe_div(
        (f.get("cash_and_equivalents") or 0) + (f.get("short_term_investments") or 0),
        f.get("current_liabilities"),
    )
    liquidity = {
        "current_ratio": _ratio_entry(current_ratio, avg.get("current_ratio")),
        "quick_ratio": _ratio_entry(quick_ratio, avg.get("quick_ratio")),
        "cash_ratio": _ratio_entry(cash_ratio, avg.get("cash_ratio")),
    }

    roa = _safe_div(f.get("net_profit_after_tax"), f.get("total_assets"))
    roe = _safe_div(f.get("net_profit_after_tax"), f.get("total_equity"))
    profitability = {
        "roa": _ratio_entry(roa, avg.get("roa")),
        "roe": _ratio_entry(roe, avg.get("roe")),
    }

    debt_ratio = _safe_div(f.get("total_liabilities"), f.get("total_capital_source"))
    self_financing_ratio = _safe_div(f.get("total_equity"), f.get("total_capital_source"))
    net_working_capital = None
    if f.get("total_equity") is not None and f.get("long_term_debt") is not None and f.get("fixed_assets_and_ltd_investments") is not None:
        net_working_capital = round(f["total_equity"] + f["long_term_debt"] - f["fixed_assets_and_ltd_investments"], 2)
    leverage = {
        # debt_ratio: below industry average is the GOOD outcome.
        "debt_ratio": _ratio_entry(debt_ratio, avg.get("debt_ratio"), lower_is_better=True),
        "self_financing_ratio": _ratio_entry(self_financing_ratio, avg.get("self_financing_ratio")),
        "net_working_capital": {
            "value": net_working_capital,
            # >0: nguồn dài hạn dư thừa tài trợ tài sản ngắn hạn (tốt).
            # <0: dùng vốn ngắn hạn tài trợ tài sản dài hạn (rủi ro thanh khoản).
            "sign": None if net_working_capital is None else ("positive" if net_working_capital >= 0 else "negative"),
        },
    }

    working_capital_turnover = _safe_div(f.get("net_revenue"), f.get("avg_current_assets"))
    receivables_turnover = _safe_div(f.get("net_revenue"), f.get("avg_accounts_receivable"))
    inventory_turnover = _safe_div(f.get("cogs"), f.get("avg_inventory"))
    asset_utilization = _safe_div(f.get("net_revenue"), f.get("avg_total_assets"))
    activity = {
        "working_capital_turnover": _ratio_entry(working_capital_turnover, avg.get("working_capital_turnover")),
        "receivables_turnover": _ratio_entry(receivables_turnover, avg.get("receivables_turnover")),
        "inventory_turnover": _ratio_entry(inventory_turnover, avg.get("inventory_turnover")),
        "asset_utilization": _ratio_entry(asset_utilization, avg.get("asset_utilization")),
    }

    # Cashflow — định tính (data-flow.md style câu hỏi đánh giá), KHÔNG phải
    # một trong 4 nhóm chấm điểm benchmark; trả kèm để tool caller có thể
    # dùng cho việc khác sau này, nhưng không tính vào count_tot_kha.
    cf_operating = f.get("cf_operating")
    cf_financing = f.get("cf_financing")
    cashflow = {
        "operating_positive": None if cf_operating is None else cf_operating > 0,
        "financing_offsets_negative_operating": (
            None if cf_operating is None or cf_financing is None else (cf_operating < 0 and cf_financing > 0)
        ),
    }

    group_rollup = {
        "LIQUIDITY": _worst_grade(list(liquidity.values())),
        "PROFITABILITY": _worst_grade(list(profitability.values())),
        # net_working_capital has no `grade` key — worst_grade ignores it via .get, so its
        # sign is applied as an explicit downgrade below instead of via ranking.
        "LEVERAGE": _worst_grade([leverage["debt_ratio"], leverage["self_financing_ratio"]]),
        "ACTIVITY": _worst_grade(list(activity.values())),
    }
    if leverage["net_working_capital"]["sign"] == "negative" and group_rollup["LEVERAGE"] is not None:
        downgraded_rank = max(_GRADE_RANK[group_rollup["LEVERAGE"]] - 1, 0)
        group_rollup["LEVERAGE"] = _GRADE_BY_RANK[downgraded_rank]

    count_tot_kha = sum(1 for g in group_rollup.values() if g in ("Tot", "Kha"))

    return {
        "outputs": {
            "liquidity": liquidity,
            "profitability": profitability,
            "leverage": leverage,
            "activity": activity,
            "cashflow": cashflow,
        },
        "group_rollup": group_rollup,
        "count_tot_kha": count_tot_kha,
        "formula_version": STATEMENT_FORMULA_VERSION,
    }


async def health(_request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": SERVER_NAME})


# Mount the FastMCP streamable-HTTP app under / and add a plain /health
# route for docker-compose healthchecks (the MCP endpoint itself expects
# MCP-protocol headers, so a bare `curl /mcp` isn't a useful liveness probe).
#
# IMPORTANT: mcp.streamable_http_app() returns a Starlette app whose
# lifespan starts the StreamableHTTPSessionManager's task group
# (`lifespan=lambda app: self.session_manager.run()`). Wrapping that app
# in a *new* outer Starlette app without re-attaching this exact lifespan
# leaves the session manager's task group uninitialized — every POST /mcp
# then 500s with "Task group is not initialized. Make sure to use run()."
# So: call streamable_http_app() first (creates mcp.session_manager as a
# side effect), then explicitly wire the same lifespan into our outer app.
mcp_asgi_app = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp_asgi_app),
    ],
    lifespan=lambda _app: mcp.session_manager.run(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
