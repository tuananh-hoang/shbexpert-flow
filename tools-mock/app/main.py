"""tools-mock — deterministic API mock for CIC / KYC / AML / valuation / LOS.

Per overview.md §3.1: has a deterministic mode enabled by seed, required
for the offline demo fallback (PRD 14.4). Every endpoint here returns
fixed data keyed only by its path parameter — no randomness, no external
calls — so a replayed run always sees the same "external system" answer.

Only `mcp-external` (Policy, Collateral, Customer 360 agents) is allowed
to call this service — see overview.md §4 "Ai KHÔNG được gọi ai".
"""
from fastapi import FastAPI, HTTPException

app = FastAPI(title="tools-mock")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Deterministic "official" valuation registry — deliberately a DIFFERENT
# number from whatever a customer's submitted valuation certificate says,
# so an agent that cross-checks both sees a real (if small) discrepancy
# instead of a suspiciously perfect match.
def _valuation_record(collateral_id: str, official_value_vnd: int) -> dict:
    """Builds one _VALUATIONS entry with the enriched fields (forced_sale_value/
    valuation_method/report_expiry_date) derived consistently from
    official_value_vnd, instead of hand-typing 3 more numbers per case.
    forced_sale_value = 85% of official_value_vnd — a conservative
    liquidation-value discount, NOT a haircut_matrix rate (that's a
    separate, later step in calculate_collateral_coverage). report_expiry_date
    = valuation_date + 12 months, the bank's OWN report-staleness rule —
    distinct from the customer-submitted certificate's expiry_date checked
    elsewhere (collateral.py's cert_days_to_expiry)."""
    return {
        "collateral_id": collateral_id,
        "official_value_vnd": official_value_vnd,
        "forced_sale_value": round(official_value_vnd * 0.85),
        "valuation_date": "2025-06-01",
        "valuation_method": "so_sanh",  # phương pháp so sánh trực tiếp — mock, không phải chọn thật theo TSBĐ
        "report_expiry_date": "2026-06-01",
        "source": "SHB_INTERNAL_REGISTRY",
    }


_VALUATIONS = {
    "C06": _valuation_record("C06", 9_500_000_000),
    "C07": _valuation_record("C07", 3_800_000_000),
    "C08": _valuation_record("C08", 4_000_000_000),
    # scripts/seed_synthetic_cases.py — official value = 0.97 x the
    # customer-submitted valuation_amount from each case's collateral[0],
    # same "differs slightly from submitted" convention as C06/C07/C08.
    "CASE-CUS-00001": _valuation_record("CASE-CUS-00001", 18_405_113_680),
    "CASE-CUS-00002": _valuation_record("CASE-CUS-00002", 21_156_561_360),
    "CASE-CUS-00003": _valuation_record("CASE-CUS-00003", 22_181_430_380),
    "CASE-CUS-00004": _valuation_record("CASE-CUS-00004", 21_434_210_280),
}


@app.get("/valuation/{collateral_id}")
def get_valuation(collateral_id: str) -> dict:
    record = _VALUATIONS.get(collateral_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no valuation on file for {collateral_id!r}")
    return record


# Mock "tổng nghĩa vụ tại MB" (dư nợ + dư bảo lãnh + dư L/C) — stands in for
# a real CIC/core-banking obligations query. Collateral allocation across
# multiple obligations/customers is explicitly OUT of scope (see plan's
# "Rủi ro" note) — this system is 1 case = 1 customer = 1 collateral today,
# so calculate_collateral_coverage compares against the FULL total below,
# no allocated_ratio needed.
_OBLIGATIONS = {
    "CUST-ANPHU": {"outstanding_loan_vnd": 4_500_000_000, "outstanding_guarantee_vnd": 0, "outstanding_lc_vnd": 0},
    "CUST-HOASEN": {"outstanding_loan_vnd": 1_800_000_000, "outstanding_guarantee_vnd": 500_000_000, "outstanding_lc_vnd": 0},
    "CUST-MINHLONG": {"outstanding_loan_vnd": 4_200_000_000, "outstanding_guarantee_vnd": 0, "outstanding_lc_vnd": 800_000_000},
}


@app.get("/credit-obligations/{customer_id}")
def get_credit_obligations(customer_id: str) -> dict:
    record = _OBLIGATIONS.get(customer_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no obligations on file for {customer_id!r}")
    total = record["outstanding_loan_vnd"] + record["outstanding_guarantee_vnd"] + record["outstanding_lc_vnd"]
    return {"customer_id": customer_id, **record, "total_obligation_vnd": total, "source": "SHB_INTERNAL_REGISTRY"}
