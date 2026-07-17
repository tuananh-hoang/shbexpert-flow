from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .io import write_json


def default_overlays(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"mutation_id": "MUT-001", "type": "MISSING_DOCUMENT", "customer_id": data["customers"][0]["customer_id"], "target": "LOAN_RESOLUTION", "expected_detector": "COMPLETENESS"},
        {"mutation_id": "MUT-002", "type": "REVENUE_MISMATCH", "customer_id": data["customers"][1]["customer_id"], "target": "2025.revenue", "expected_detector": "FINANCIAL_CONFLICT"},
        {"mutation_id": "MUT-003", "type": "CIC_NEAR_MATCH", "customer_id": data["customers"][2]["customer_id"], "target": "KYC", "expected_detector": "KYC_AML_REVIEW"},
        {"mutation_id": "MUT-004", "type": "VALUATION_EXPIRED", "customer_id": data["customers"][3]["customer_id"], "target": "COLLATERAL", "expected_detector": "COLLATERAL_VALIDITY"},
    ]


def assemble_case(data: dict[str, Any], customer_id: str, overlays: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    app = next(row for row in data["applications"] if row["customer_id"] == customer_id)
    case = {"case_id": f"CASE-{customer_id}", "customer": next(row for row in data["customers"] if row["customer_id"] == customer_id), "application": app,
            "legal_documents": [row for row in data["legal_documents"] if row["customer_id"] == customer_id],
            "financials": [row for row in data["financials"] if row["customer_id"] == customer_id],
            "transactions": [row for row in data["transactions"] if row["customer_id"] == customer_id],
            "cic_reports": [row for row in data["cic_reports"] if row["customer_id"] == customer_id],
            "kyc_screenings": [row for row in data["kyc_screenings"] if row["customer_id"] == customer_id],
            "collateral": [row for row in data["collateral"] if row["application_id"] == app["application_id"]],
            "relationships": [row for row in data["relationships"] if row["customer_id"] == customer_id],
            "policy_snapshot_id": app["policy_snapshot_id"], "as_of_date": data["manifest"]["as_of_date"]}
    case = deepcopy(case)
    for overlay in overlays or []:
        if overlay["type"] == "MISSING_DOCUMENT": case["legal_documents"] = [x for x in case["legal_documents"] if x["document_type"] != overlay["target"]]
        elif overlay["type"] == "REVENUE_MISMATCH":
            for row in case["financials"]:
                if row["period"] == "2025": row["reported_revenue"] = int(row["revenue"] * .89)
        elif overlay["type"] == "CIC_NEAR_MATCH": case["kyc_screenings"][0].update({"match_status": "POTENTIAL_MATCH", "match_score": .87, "matched_mock_entity_id": "WATCH-MOCK-001", "analyst_status": "PENDING_REVIEW"})
        elif overlay["type"] == "VALUATION_EXPIRED":
            for row in case["collateral"]: row["valuation_date"] = str(date.fromisoformat(row["valuation_date"]) - timedelta(days=730))
    case["applied_mutations"] = [row["mutation_id"] for row in overlays or []]
    return case


def export_case(case: dict[str, Any], output: Path) -> None:
    write_json(output / case["case_id"] / "case.json", case)
