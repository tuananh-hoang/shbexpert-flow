"""Adapter: imports the 4 pre-assembled cases from the synthetic-data-pipeline
branch (`artifacts/cases/CASE-CUS-0000{1..4}/case.json`) into real system
Cases — Document + ExtractedField rows with REAL rendered PDFs (reusing
scripts/pdf_utils.py unchanged), then triggers a real analyze job per case.

Why this exists (see the plan this was built from): the synthetic-data-
pipeline's case bundles are pure structured JSON — deliberately no PDFs,
no page/bbox — because that pipeline's own goal is "test logic, not OCR".
Our system's Evidence Viewer needs a real rendered document + accurate
bbox, so this script is the translation layer, not a passthrough.

Field mapping — what's directly available vs. what had to be DERIVED
(documented here, not hidden, and also printed into the rendered PDF text
itself so nobody mistakes a derived number for an extracted one):
  - revenue_2025            <- financials[period="2025"].revenue (direct)
  - ebitda_2025              = profit_before_tax + interest_expense
                                (no D&A field in the source data, so the
                                usual +D&A add-back is omitted — this is
                                an approximation, not a real EBITDA calc)
  - debt_service_annual      = interest_expense + debt / 5
                                (source has a debt BALANCE, not a
                                repayment schedule — assumes existing
                                debt amortizes over 5 years)
  - revenue_2025_tax_filing <- financials[2025].reported_revenue if
                                present (only CASE-CUS-00002, the
                                MUT-002 revenue-mismatch case), else
                                falls back to `revenue` itself (no
                                fabricated mismatch for the other 3 cases)
  - valuation_amount        <- collateral[0].valuation_amount (direct)
  - valuation_expiry_date    = collateral[0].valuation_date + 365 days
                                (source has a valuation DATE, not an
                                expiry — assumes a 12-month validity
                                window)

Known limitation (see plan): 2 of the 4 planted mutations won't manifest
through this system as originally intended —
  - MUT-001 (missing LOAN_RESOLUTION doc, CASE-1): LOAN_RESOLUTION isn't
    one of the 4 doc_types gate G1 checks, so this case clears G1 normally.
  - MUT-003 (CIC/KYC near-match, CASE-3): no KYC/AML agent exists yet
    (gate G2 is a mocked PASS) — this case runs clean too.
Only MUT-002 (CASE-2, revenue mismatch) and MUT-004 (CASE-4, expired
valuation) actually trigger the agent behavior they were designed to test.

Run with: `docker compose run --rm api python -m scripts.seed_synthetic_cases`
Idempotent per case — skips any CASE-CUS-0000N that already exists.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import redis

from shared.db import get_session
from shared.models import Case, Document, ExtractedField
from shared.queue import ANALYZE_QUEUE
from shared.storage import upload_bytes

from scripts.pdf_utils import render_document_pdf

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CASES_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "cases"
CASE_IDS = ["CASE-CUS-00001", "CASE-CUS-00002", "CASE-CUS-00003", "CASE-CUS-00004"]

_DEBT_AMORTIZATION_YEARS = 5
_VALUATION_VALIDITY_DAYS = 365


def _fmt_vnd(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".") + " VND"


def _load_case(case_id: str) -> dict:
    path = CASES_DIR / case_id / "case.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_docs(raw: dict) -> list[dict]:
    customer = raw["customer"]
    fin2025 = next(x for x in raw["financials"] if x["period"] == "2025")
    col = raw["collateral"][0]
    bizreg = next(x for x in raw["legal_documents"] if x["document_type"] == "BUSINESS_REGISTRATION")

    ebitda = fin2025["profit_before_tax"] + fin2025["interest_expense"]
    debt_service = fin2025["interest_expense"] + fin2025["debt"] / _DEBT_AMORTIZATION_YEARS
    tax_filing_revenue = fin2025.get("reported_revenue", fin2025["revenue"])
    valuation_expiry = (
        date.fromisoformat(col["valuation_date"]) + timedelta(days=_VALUATION_VALIDITY_DAYS)
    ).isoformat()

    return [
        {
            "key": "bizreg",
            "doc_type": "business_registration",
            "filename": "dang_ky_kinh_doanh.pdf",
            "title": f"GIAY CHUNG NHAN DANG KY DOANH NGHIEP - {customer['legal_name']}",
            "lines": [
                ("Ma so thue", customer["mock_tax_id"], None),
                ("So giay chung nhan", bizreg["document_number"], None),
                ("Ngay cap", bizreg["issued_at"], None),
            ],
            "field_defs": {},
        },
        {
            "key": "bctc",
            "doc_type": "financial_statement",
            "filename": "bctc_2025.pdf",
            "title": f"BAO CAO KET QUA KINH DOANH 2025 - {customer['legal_name']}",
            "lines": [
                ("Doanh thu thuan", _fmt_vnd(fin2025["revenue"]), "revenue_2025"),
                (
                    "EBITDA (uoc tinh = LNTT + chi phi lai vay, khong co du lieu khau hao)",
                    _fmt_vnd(ebitda),
                    "ebitda_2025",
                ),
                (
                    "Nghia vu tra no goc + lai hang nam (uoc tinh, gia dinh tat toan 5 nam)",
                    _fmt_vnd(debt_service),
                    "debt_service_annual",
                ),
            ],
            "field_defs": {
                "revenue_2025": ({"amount_vnd": fin2025["revenue"]}, 0.97),
                "ebitda_2025": ({"amount_vnd": round(ebitda)}, 0.6),
                "debt_service_annual": ({"amount_vnd": round(debt_service)}, 0.6),
            },
        },
        {
            "key": "tax",
            "doc_type": "tax_filing",
            "filename": "to_khai_thue_2025.pdf",
            "title": f"TO KHAI QUYET TOAN THUE TNDN 2025 - {customer['legal_name']}",
            "lines": [("Doanh thu chiu thue", _fmt_vnd(tax_filing_revenue), "revenue_2025_tax_filing")],
            "field_defs": {"revenue_2025_tax_filing": ({"amount_vnd": tax_filing_revenue}, 0.96)},
        },
        {
            "key": "valuation",
            "doc_type": "valuation_certificate",
            "filename": "chung_thu_dinh_gia.pdf",
            "title": "CHUNG THU DINH GIA TAI SAN BAO DAM",
            "lines": [
                ("Gia tri dinh gia", _fmt_vnd(col["valuation_amount"]), "valuation_amount"),
                ("Ngay dinh gia", col["valuation_date"], None),
                (
                    "Hieu luc den (uoc tinh, gia dinh hieu luc 12 thang)",
                    valuation_expiry,
                    "valuation_expiry_date",
                ),
            ],
            "field_defs": {
                "valuation_amount": ({"amount_vnd": col["valuation_amount"]}, 0.9),
                "valuation_expiry_date": ({"date": valuation_expiry}, 0.9),
            },
        },
    ]


def _seed_one(case_id: str) -> bool:
    with get_session() as session:
        if session.get(Case, case_id) is not None:
            print(f"case {case_id} already exists — skipping (idempotent)")
            return False

        raw = _load_case(case_id)
        session.add(
            Case(
                case_id=case_id,
                customer_id=raw["customer"]["customer_id"],
                product="SME_WC",
                requested_facility={
                    "amount_vnd": raw["application"]["requested_amount"],
                    "tenor_months": raw["application"]["tenor_months"],
                    "as_of_date": raw["as_of_date"],
                },
                owner="rm1",
                state="ANALYZING",
                version=1,
            )
        )
        session.flush()

        for doc in _build_docs(raw):
            pdf_bytes, bbox_by_field_key = render_document_pdf(doc["title"], doc["lines"])
            sha256 = upload_bytes(
                key=f"{case_id}/{doc['filename']}",
                data=pdf_bytes,
                content_type="application/pdf",
            )
            row = Document(
                case_id=case_id,
                doc_type=doc["doc_type"],
                minio_key=f"{case_id}/{doc['filename']}",
                sha256=sha256,
                review_status="COMPLETE",
            )
            session.add(row)
            session.flush()
            print(f"  uploaded {doc['filename']} -> document_id={row.document_id}")

            for field_key, (value, confidence) in doc["field_defs"].items():
                bbox = bbox_by_field_key[field_key]
                session.add(
                    ExtractedField(
                        document_id=row.document_id,
                        field_key=field_key,
                        value=value,
                        confidence=confidence,
                        page=bbox["page"],
                        bbox={"x0": bbox["x0"], "y0": bbox["y0"], "x1": bbox["x1"], "y1": bbox["y1"]},
                    )
                )

        print(f"seeded case {case_id} ({raw['customer']['legal_name']})")
        return True


def main() -> None:
    r = redis.from_url(REDIS_URL)
    try:
        for case_id in CASE_IDS:
            seeded = _seed_one(case_id)
            if seeded:
                r.lpush(ANALYZE_QUEUE, json.dumps({"case_id": case_id}))
                print(f"enqueued analyze job for case {case_id}")
    finally:
        r.close()


if __name__ == "__main__":
    main()
