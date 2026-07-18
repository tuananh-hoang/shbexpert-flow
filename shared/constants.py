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


# ---------------------------------------------------------------------------
# Phân luồng xanh/đỏ khi tiếp nhận hồ sơ — spec
# docs/superpowers/specs/2026-07-19-intake-routing-design.md §4.
#
# Luồng xanh (ACAS-SLINK, tự động 100%, không qua Credit Officer) chỉ nhận
# thấu chi MicroSME trong hạn mức tự động. Mọi trường hợp khác là luồng đỏ.
#
# Dùng MÃ sản phẩm chứ không phải tên tiếng Việt: chuỗi có dấu làm khóa so
# sánh thì đổi chính tả là vỡ, mà lỗi lại im lặng — hồ sơ rơi nhầm luồng
# thay vì báo lỗi.
#
# Ba giá trị dưới đây là số của prototype demo (AUTO_APPROVAL_CEILING_VND,
# AUTO_APPROVAL_ELIGIBLE_PRODUCTS trong shb_credit_agents/src/data/
# registries.ts), KHÔNG phải chính sách hay khẩu vị rủi ro thật của SHB.
# ---------------------------------------------------------------------------

PRODUCT_LABEL_VI: dict[str, str] = {
    "MICRO_OD": "Thấu chi doanh nghiệp",
    "SME_WC": "Vay vốn lưu động SME",
    "SME_TERM": "Vay đầu tư tài sản cố định",
}

VALID_PRODUCTS: frozenset[str] = frozenset(PRODUCT_LABEL_VI)

VALID_SEGMENTS: frozenset[str] = frozenset({"SME", "MICROSME"})

VALID_CHANNELS: frozenset[str] = frozenset({"RM_LMS", "MOBILE_KHDN"})

AUTO_APPROVAL_ELIGIBLE_PRODUCTS: frozenset[str] = frozenset({"MICRO_OD"})
AUTO_APPROVAL_SEGMENT = "MICROSME"
AUTO_APPROVAL_CEILING_VND = 300_000_000
