"""Seed case C08 — Minh Long Trading Co. — a WEAKER-fundamentals narrative
for the Application Queue: DSCR just below the 1.3 support threshold
(Financial Agent -> CAUTION), and a valuation certificate expiring soon
(19 days, well under the 60-day rule) so Collateral Agent independently
lands on CAUTION too via the expiry rule — both agents AGREE (CAUTION),
so unlike C06 this does NOT trigger the challenge loop; it exercises a
different real path: hard gates all PASS (revenue reconciles fine, no
NEED_DATA), but the scorecard comes out weaker due to genuinely weaker
numbers — a distinct, non-fabricated demo point from C06's conflict-loop
scenario and C07's clean-approval scenario.

Documents are REAL PDFs (scripts/pdf_utils.py) — see seed_case_c06.py.

Also pushes a real analyze job to Redis after seeding (see seed_case_c07.py
for why — queue rows must be backed by a genuine pipeline run).

Run with: `docker compose run --rm api python -m scripts.seed_case_c08`
Idempotent — exits early if case C08 already exists.
"""
from __future__ import annotations

import json
import os

import redis

from shared.db import get_session
from shared.models import Case, Document, ExtractedField
from shared.queue import ANALYZE_QUEUE
from shared.storage import upload_bytes

from scripts.pdf_utils import render_document_pdf

CASE_ID = "C08"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

DOCS = [
    {
        "key": "bctc",
        "doc_type": "financial_statement",
        "filename": "bctc_2025.pdf",
        "title": "BAO CAO KET QUA KINH DOANH 2025 - MINH LONG TRADING",
        "lines": [
            ("Doanh thu thuan", "20.000.000.000 VND", "revenue_2025"),
            ("EBITDA", "2.000.000.000 VND", "ebitda_2025"),
            ("Nghia vu tra no goc + lai hang nam (uoc tinh)", "1.700.000.000 VND", "debt_service_annual"),
        ],
        "field_defs": {
            "revenue_2025": ({"amount_vnd": 20_000_000_000}, 0.97),
            "ebitda_2025": ({"amount_vnd": 2_000_000_000}, 0.95),
            "debt_service_annual": ({"amount_vnd": 1_700_000_000}, 0.94),
        },
    },
    {
        "key": "tax",
        "doc_type": "tax_filing",
        "filename": "to_khai_thue_2025.pdf",
        "title": "TO KHAI QUYET TOAN THUE TNDN 2025 - MINH LONG TRADING",
        "lines": [("Doanh thu chiu thue", "19.500.000.000 VND", "revenue_2025_tax_filing")],
        "field_defs": {"revenue_2025_tax_filing": ({"amount_vnd": 19_500_000_000}, 0.96)},
    },
    {
        "key": "valuation",
        "doc_type": "valuation_certificate",
        "filename": "chung_thu_dinh_gia.pdf",
        "title": "CHUNG THU DINH GIA TAI SAN BAO DAM",
        "lines": [
            ("Gia tri dinh gia", "4.200.000.000 VND", "valuation_amount"),
            ("Ngay dinh gia", "2026-01-01", None),
            ("Hieu luc den", "2026-07-20", "valuation_expiry_date"),
        ],
        "field_defs": {
            "valuation_amount": ({"amount_vnd": 4_200_000_000}, 0.9),
            "valuation_expiry_date": ({"date": "2026-07-20"}, 0.9),
        },
    },
    {
        "key": "dkkd",
        "doc_type": "business_registration",
        "filename": "dang_ky_kinh_doanh.pdf",
        "title": "GIAY CHUNG NHAN DANG KY DOANH NGHIEP - MINH LONG TRADING",
        "lines": [
            ("Vu Minh Long", "70%", "ownership_structure"),
            ("Dang Thi Lan", "30%", "ownership_structure"),
        ],
        "field_defs": {
            "ownership_structure": (
                {"owners": [{"name": "Vu Minh Long", "pct": 70}, {"name": "Dang Thi Lan", "pct": 30}]},
                0.93,
            )
        },
    },
    {
        "key": "bank",
        "doc_type": "bank_transactions",
        "filename": "giao_dich_ngan_hang.pdf",
        "title": "SAO KE GIAO DICH TAI KHOAN - MINH LONG TRADING",
        "lines": [("Ty trong doanh thu tu khach hang lon nhat (Buyer Y)", "48%", "top_customer_concentration")],
        "field_defs": {"top_customer_concentration": ({"buyer": "Buyer Y", "pct": 48}, 0.85)},
    },
]


def main() -> None:
    with get_session() as session:
        if session.get(Case, CASE_ID) is not None:
            print(f"case {CASE_ID} already exists — nothing to do (script is idempotent)")
            return

        session.add(
            Case(
                case_id=CASE_ID,
                customer_id="CUST-MINHLONG",
                product="SME_WC",
                requested_facility={
                    "amount_vnd": 5_000_000_000,
                    "tenor_months": 12,
                    "as_of_date": "2026-07-01",
                },
                owner="rm1",
                state="ANALYZING",
                version=1,
            )
        )
        session.flush()

        for doc in DOCS:
            pdf_bytes, bbox_by_field_key = render_document_pdf(doc["title"], doc["lines"])
            sha256 = upload_bytes(
                key=f"{CASE_ID}/{doc['filename']}",
                data=pdf_bytes,
                content_type="application/pdf",
            )
            row = Document(
                case_id=CASE_ID,
                doc_type=doc["doc_type"],
                minio_key=f"{CASE_ID}/{doc['filename']}",
                sha256=sha256,
                review_status="COMPLETE",
            )
            session.add(row)
            session.flush()
            print(f"uploaded {doc['filename']} -> document_id={row.document_id}")

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

        total_fields = sum(len(d["field_defs"]) for d in DOCS)
        print(f"seeded case {CASE_ID} with {len(DOCS)} documents and {total_fields} extracted fields")

    r = redis.from_url(REDIS_URL)
    try:
        r.lpush(ANALYZE_QUEUE, json.dumps({"case_id": CASE_ID}))
        print(f"enqueued analyze job for case {CASE_ID}")
    finally:
        r.close()


if __name__ == "__main__":
    main()
