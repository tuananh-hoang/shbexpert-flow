"""Seed golden case C06 — An Phú Packaging (data-flow.md §11 flagship demo).

Per the user's constraint, this script stands in for the Document
Processing Pipeline / OCR entirely: it writes `documents` + already-"OCR'd"
`extracted_fields` directly. Documents are REAL PDFs (scripts/pdf_utils.py,
reportlab) — not placeholder .txt files — so the Evidence Viewer (Screen 3,
FE_flow.jpeg) can render the actual page with a highlight box over the
cited line. Bbox values come directly from what pdf_utils drew, not
hand-invented numbers.

Narrative baked into the seed data (matches the docs' flagship case):
  - Requested: 8 tỷ VND / 12 tháng vốn lưu động.
  - Revenue mismatch 11% between BCTC (84.0B) and tax filing (74.76B) —
    the DataConflict that should surface in Phase 3/4.
  - Valuation certificate expiring 2026-08-01 (soon after the as_of_date).
  - Ownership structure with two owners over the 20% "related party"
    threshold — Nguyễn Văn A 60%, Trần Thị B 25%.
  - 42% revenue concentration on a single buyer.

Run with: `docker compose exec api python -m scripts.seed_case_c06`
Idempotent — exits early if case C06 already exists.
"""
from __future__ import annotations

from shared.db import get_session
from shared.models import Case, Document, ExtractedField
from shared.storage import upload_bytes

from scripts.pdf_utils import render_document_pdf

CASE_ID = "C06"

# Each doc: (key, doc_type, filename, title, lines, field_defs)
# lines: [(label, display_text, field_key_or_None), ...] — drives the PDF.
# field_defs: {field_key: (structured_value, confidence)} — drives ExtractedField
#             (page/bbox come from render_document_pdf's return, not here).
DOCS = [
    {
        "key": "bctc",
        "doc_type": "financial_statement",
        "filename": "bctc_2025.pdf",
        "title": "BAO CAO KET QUA KINH DOANH 2025 - AN PHU PACKAGING",
        "lines": [
            ("Doanh thu thuan", "84.000.000.000 VND", "revenue_2025"),
            ("EBITDA", "9.200.000.000 VND", "ebitda_2025"),
            ("Nghia vu tra no goc + lai hang nam (uoc tinh)", "5.350.000.000 VND", "debt_service_annual"),
        ],
        "field_defs": {
            "revenue_2025": ({"amount_vnd": 84_000_000_000}, 0.97),
            "ebitda_2025": ({"amount_vnd": 9_200_000_000}, 0.95),
            "debt_service_annual": ({"amount_vnd": 5_350_000_000}, 0.94),
        },
    },
    {
        "key": "tax",
        "doc_type": "tax_filing",
        "filename": "to_khai_thue_2025.pdf",
        "title": "TO KHAI QUYET TOAN THUE TNDN 2025 - AN PHU PACKAGING",
        "lines": [("Doanh thu chiu thue", "74.760.000.000 VND", "revenue_2025_tax_filing")],
        "field_defs": {"revenue_2025_tax_filing": ({"amount_vnd": 74_760_000_000}, 0.96)},
    },
    {
        "key": "valuation",
        "doc_type": "valuation_certificate",
        "filename": "chung_thu_dinh_gia.pdf",
        "title": "CHUNG THU DINH GIA TAI SAN BAO DAM",
        "lines": [
            ("Gia tri dinh gia", "10.000.000.000 VND", "valuation_amount"),
            ("Ngay dinh gia", "2025-08-01", None),
            ("Hieu luc den", "2026-08-01", "valuation_expiry_date"),
        ],
        "field_defs": {
            "valuation_amount": ({"amount_vnd": 10_000_000_000}, 0.9),
            "valuation_expiry_date": ({"date": "2026-08-01"}, 0.9),
        },
    },
    {
        "key": "dkkd",
        "doc_type": "business_registration",
        "filename": "dang_ky_kinh_doanh.pdf",
        "title": "GIAY CHUNG NHAN DANG KY DOANH NGHIEP - AN PHU PACKAGING",
        "lines": [
            ("Nguyen Van A", "60%", "ownership_structure"),
            ("Tran Thi B", "25%", "ownership_structure"),
            ("Cong ty XYZ", "15%", "ownership_structure"),
        ],
        "field_defs": {
            "ownership_structure": (
                {
                    "owners": [
                        {"name": "Nguyen Van A", "pct": 60},
                        {"name": "Tran Thi B", "pct": 25},
                        {"name": "Cong ty XYZ", "pct": 15},
                    ]
                },
                0.93,
            )
        },
    },
    {
        "key": "bank",
        "doc_type": "bank_transactions",
        "filename": "giao_dich_ngan_hang.pdf",
        "title": "SAO KE GIAO DICH TAI KHOAN - AN PHU PACKAGING",
        "lines": [("Ty trong doanh thu tu khach hang lon nhat (Buyer A)", "42%", "top_customer_concentration")],
        "field_defs": {"top_customer_concentration": ({"buyer": "Buyer A", "pct": 42}, 0.85)},
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
                customer_id="CUST-ANPHU",
                product="SME_WC",
                requested_facility={
                    "amount_vnd": 8_000_000_000,
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


if __name__ == "__main__":
    main()
