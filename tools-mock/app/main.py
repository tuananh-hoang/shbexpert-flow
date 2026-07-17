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
_VALUATIONS = {
    "C06": {
        "collateral_id": "C06",
        "official_value_vnd": 9_500_000_000,
        "valuation_date": "2025-06-01",
        "source": "SHB_INTERNAL_REGISTRY",
    },
    "C07": {
        "collateral_id": "C07",
        "official_value_vnd": 3_800_000_000,
        "valuation_date": "2025-06-01",
        "source": "SHB_INTERNAL_REGISTRY",
    },
    "C08": {
        "collateral_id": "C08",
        "official_value_vnd": 4_000_000_000,
        "valuation_date": "2025-06-01",
        "source": "SHB_INTERNAL_REGISTRY",
    },
}


@app.get("/valuation/{collateral_id}")
def get_valuation(collateral_id: str) -> dict:
    record = _VALUATIONS.get(collateral_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no valuation on file for {collateral_id!r}")
    return record
