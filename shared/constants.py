"""Small cross-service constants — values both `api` and `worker` need to
agree on, without either importing the other's package. Started with
REQUIRED_DOC_TYPES: previously defined only inside
worker/app/graph/decision.py (where gate G1 checks it), but the Document
Completeness dashboard widget needs the exact same list on the `api` side
too — a single source here means the two can never silently drift apart.
"""
from __future__ import annotations

REQUIRED_DOC_TYPES: frozenset[str] = frozenset(
    {"financial_statement", "tax_filing", "valuation_certificate", "business_registration"}
)

# ---------------------------------------------------------------------------
# Standard financial-statement ratio analysis — worker/app/agents/financial.py
# + mcp-deterministic/app/server.py::calculate_statement_ratios. This is
# textbook financial-statement analysis (balance sheet / income statement /
# cashflow statement ratios + industry-benchmark grading), not specific to
# any one bank — kept here (not duplicated in worker) so `financial.py`'s
# REQUIRED_FIELDS guardrail and the tool's ratio_table keys can never drift
# apart the same way REQUIRED_DOC_TYPES above stays single-sourced.
# ---------------------------------------------------------------------------

# Fields a Financial Agent run must have before it may call
# calculate_statement_ratios — missing any one of these means the ratio
# grading would be either undefined (division by a missing denominator) or
# materially incomplete, so the agent must return NEED_DATA instead of
# silently omitting a group. `historical_data_years` enforces the "minimum
# 3 consecutive years, or a stated reason for a newly-formed business" rule.
REQUIRED_STATEMENT_FIELDS: frozenset[str] = frozenset(
    {
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_capital_source",
        "current_assets_total",
        "current_liabilities",
        "cash_and_equivalents",
        "accounts_receivable",
        "inventory",
        "net_revenue",
        "cogs",
        "net_profit_after_tax",
        "cf_operating",
        "historical_data_years",
    }
)

# Mock industry-average ratio table used to grade each computed ratio as
# Tốt/Khá/Trung bình/Kém (ratio_vs_avg >= 1.2 / >= 1.0 / >= 0.7 / else — see
# calculate_statement_ratios::grade_vs_benchmark). Generic demo values, not
# sourced from a real industry survey — swap for a real per-industry
# benchmark table before using this for an actual credit decision.
STATEMENT_BENCHMARK_VERSION = "BENCH-0.1-MOCK"

INDUSTRY_AVG_RATIOS: dict[str, float] = {
    "current_ratio": 1.5,
    "quick_ratio": 1.0,
    "cash_ratio": 0.5,
    "roa": 0.06,
    "roe": 0.14,
    "debt_ratio": 0.55,
    "self_financing_ratio": 0.45,
    "working_capital_turnover": 2.5,
    "receivables_turnover": 6.0,
    "inventory_turnover": 5.0,
    "asset_utilization": 1.2,
}
