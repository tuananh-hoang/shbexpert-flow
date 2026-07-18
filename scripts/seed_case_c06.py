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

import datetime as dt

from shared.db import get_session
from shared.models import (
    Case,
    ChecklistCompletion,
    CollateralRegistry,
    CoOwnerRegistry,
    Document,
    ExtractedField,
    LegalDocumentStore,
)
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
            # Same figure as revenue_2025, seeded under the field_key the
            # standard-ratio formulas expect (activity turnover ratios use
            # "net_revenue" — mcp-deterministic/app/server.py) — kept as a
            # separate line/field_key rather than renaming revenue_2025
            # itself, since revenue_2025 also feeds the unrelated DSCR calc.
            ("Doanh thu thuan (dung cho phan tich ty so BCTC)", "84.000.000.000 VND", "net_revenue"),
            ("EBITDA", "9.200.000.000 VND", "ebitda_2025"),
            ("Nghia vu tra no goc + lai hang nam (uoc tinh)", "5.350.000.000 VND", "debt_service_annual"),
            # Standard financial-statement ratio analysis fields (balance
            # sheet / income statement / cashflow statement / period-average)
            # — worker/app/agents/financial.py::run_financial_agent.
            ("Tien va tuong duong tien", "5.000.000.000 VND", "cash_and_equivalents"),
            ("Dau tu ngan han", "2.000.000.000 VND", "short_term_investments"),
            ("Phai thu khach hang", "10.000.000.000 VND", "accounts_receivable"),
            ("Hang ton kho", "8.000.000.000 VND", "inventory"),
            ("Tong tai san luu dong", "25.000.000.000 VND", "current_assets_total"),
            ("Tai san co dinh va dau tu dai han", "35.000.000.000 VND", "fixed_assets_and_ltd_investments"),
            ("Tong tai san", "60.000.000.000 VND", "total_assets"),
            ("No ngan han", "15.000.000.000 VND", "current_liabilities"),
            ("No dai han", "15.000.000.000 VND", "long_term_debt"),
            ("Tong no phai tra", "30.000.000.000 VND", "total_liabilities"),
            ("Von chu so huu", "30.000.000.000 VND", "total_equity"),
            ("Tong nguon von", "60.000.000.000 VND", "total_capital_source"),
            ("Loi nhuan sau thue", "6.000.000.000 VND", "net_profit_after_tax"),
            ("Gia von hang ban", "60.000.000.000 VND", "cogs"),
            ("Dong tien tu hoat dong kinh doanh", "7.000.000.000 VND", "cf_operating"),
            ("Dong tien tu hoat dong dau tu", "-3.000.000.000 VND", "cf_investing"),
            ("Dong tien tu hoat dong tai chinh", "-2.000.000.000 VND", "cf_financing"),
            ("TSLD binh quan", "24.000.000.000 VND", "avg_current_assets"),
            ("Phai thu binh quan", "9.000.000.000 VND", "avg_accounts_receivable"),
            ("Ton kho binh quan", "7.500.000.000 VND", "avg_inventory"),
            ("Tong tai san binh quan", "57.000.000.000 VND", "avg_total_assets"),
            ("So nam so lieu tai chinh lien tuc", "3 nam", "historical_data_years"),
        ],
        "field_defs": {
            "revenue_2025": ({"amount_vnd": 84_000_000_000}, 0.97),
            "net_revenue": ({"amount_vnd": 84_000_000_000}, 0.97),
            "ebitda_2025": ({"amount_vnd": 9_200_000_000}, 0.95),
            "debt_service_annual": ({"amount_vnd": 5_350_000_000}, 0.94),
            "cash_and_equivalents": ({"amount_vnd": 5_000_000_000}, 0.95),
            "short_term_investments": ({"amount_vnd": 2_000_000_000}, 0.93),
            "accounts_receivable": ({"amount_vnd": 10_000_000_000}, 0.95),
            "inventory": ({"amount_vnd": 8_000_000_000}, 0.94),
            "current_assets_total": ({"amount_vnd": 25_000_000_000}, 0.95),
            "fixed_assets_and_ltd_investments": ({"amount_vnd": 35_000_000_000}, 0.93),
            "total_assets": ({"amount_vnd": 60_000_000_000}, 0.96),
            "current_liabilities": ({"amount_vnd": 15_000_000_000}, 0.95),
            "long_term_debt": ({"amount_vnd": 15_000_000_000}, 0.94),
            "total_liabilities": ({"amount_vnd": 30_000_000_000}, 0.95),
            "total_equity": ({"amount_vnd": 30_000_000_000}, 0.95),
            "total_capital_source": ({"amount_vnd": 60_000_000_000}, 0.95),
            "net_profit_after_tax": ({"amount_vnd": 6_000_000_000}, 0.95),
            "cogs": ({"amount_vnd": 60_000_000_000}, 0.94),
            "cf_operating": ({"amount_vnd": 7_000_000_000}, 0.93),
            "cf_investing": ({"amount_vnd": -3_000_000_000}, 0.9),
            "cf_financing": ({"amount_vnd": -2_000_000_000}, 0.9),
            "avg_current_assets": ({"amount_vnd": 24_000_000_000}, 0.9),
            "avg_accounts_receivable": ({"amount_vnd": 9_000_000_000}, 0.9),
            "avg_inventory": ({"amount_vnd": 7_500_000_000}, 0.9),
            "avg_total_assets": ({"amount_vnd": 57_000_000_000}, 0.9),
            "historical_data_years": ({"years": 3}, 0.9),
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

        # Collateral & Legal Agent domain (shared/models.py "Collateral &
        # Legal domain" section) — collateral_id == case_id convention.
        # collateral_type "valuation_certificate" must match
        # worker/app/agents/collateral.py::COLLATERAL_TYPE exactly.
        session.add(
            CollateralRegistry(
                collateral_id=CASE_ID,
                owner_name="Nguyen Van A",
                owner_id="CUST-ANPHU",  # matches Case.customer_id -> ownership_verified=True
                registration_number="GCN-AP-2020-0456",
                registration_date=dt.datetime(2020, 1, 15, tzinfo=dt.timezone.utc),
                registration_authority="So Tai nguyen va Moi truong TP.HCM",
                collateral_type="valuation_certificate",
            )
        )
        # No ownership_encumbrance rows — collateral is unencumbered, keeps
        # C06's deliberate conflicts scoped to revenue/valuation-expiry only
        # (data-flow.md §11), not adding a new ownership dispute on top.
        session.add(
            LegalDocumentStore(
                collateral_id=CASE_ID,
                doc_type="Giay chung nhan quyen su dung dat",
                issue_date=dt.datetime(2020, 1, 15, tzinfo=dt.timezone.utc),
                is_original=True,
                verification_status="VERIFIED",
            )
        )
        for co_owner, pct in [("Tran Thi B", 25), ("Cong ty XYZ", 15)]:
            session.add(CoOwnerRegistry(collateral_id=CASE_ID, co_owner_id=co_owner, consent_status="CONFIRMED"))
        for checklist_id in ("LC-VALUATION-EXPIRY-60D", "LC-VALUATION-APPRAISER-LICENSE"):
            session.add(
                ChecklistCompletion(
                    collateral_id=CASE_ID,
                    checklist_id=checklist_id,
                    completion_status="completed",
                    completed_date=dt.datetime(2025, 8, 1, tzinfo=dt.timezone.utc),
                    responsible_party="rm1",
                )
            )
        print(f"seeded collateral domain rows for case {CASE_ID}")


if __name__ == "__main__":
    main()
