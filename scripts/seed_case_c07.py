"""Seed case C07 — Hoa Sen Export Co. — a CLEAN approval narrative for the
Application Queue (frontend-flow plan Phase 1): revenue matches between
BCTC and tax filing (well under the 5% REV-RECON v2.0 threshold, so
Policy Agent lands on SUPPORT, no NEED_DATA), DSCR comfortably above the
1.3 support threshold, and a valuation certificate far from expiry — so
Financial and Collateral agents agree (both SUPPORT on
COLLATERAL_COVERAGE), no conflict round is ever triggered.

Documents are REAL PDFs (scripts/pdf_utils.py) — see seed_case_c06.py for
why (Evidence Viewer needs bbox that matches an actual rendered page).

Unlike C06, this script also PUSHES an analyze job to Redis after seeding
— the Application Queue needs at least one case that's already been
through the real pipeline (Findings/Decision genuinely computed, not
fabricated) so the queue shows a completed example alongside a fresh one.

Run with: `docker compose run --rm api python -m scripts.seed_case_c07`
Idempotent — exits early if case C07 already exists.
"""
from __future__ import annotations

import json
import os

import redis

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
from shared.queue import ANALYZE_QUEUE
from shared.storage import upload_bytes

from scripts.pdf_utils import render_document_pdf

CASE_ID = "C07"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

DOCS = [
    {
        "key": "bctc",
        "doc_type": "financial_statement",
        "filename": "bctc_2025.pdf",
        "title": "BAO CAO KET QUA KINH DOANH 2025 - HOA SEN EXPORT",
        "lines": [
            ("Doanh thu thuan", "40.000.000.000 VND", "revenue_2025"),
            # See seed_case_c06.py for why this is a separate field_key from
            # revenue_2025 (same figure, different consumer: activity ratios).
            ("Doanh thu thuan (dung cho phan tich ty so BCTC)", "40.000.000.000 VND", "net_revenue"),
            ("EBITDA", "5.500.000.000 VND", "ebitda_2025"),
            ("Nghia vu tra no goc + lai hang nam (uoc tinh)", "2.800.000.000 VND", "debt_service_annual"),
            # Standard financial-statement ratio analysis fields — strong
            # narrative (all 4 groups grade Tot/Kha, matches this case's
            # clean-approval story, see module docstring).
            ("Tien va tuong duong tien", "6.000.000.000 VND", "cash_and_equivalents"),
            ("Dau tu ngan han", "2.000.000.000 VND", "short_term_investments"),
            ("Phai thu khach hang", "6.000.000.000 VND", "accounts_receivable"),
            ("Hang ton kho", "4.000.000.000 VND", "inventory"),
            ("Tong tai san luu dong", "18.000.000.000 VND", "current_assets_total"),
            ("Tai san co dinh va dau tu dai han", "17.000.000.000 VND", "fixed_assets_and_ltd_investments"),
            ("Tong tai san", "35.000.000.000 VND", "total_assets"),
            ("No ngan han", "8.000.000.000 VND", "current_liabilities"),
            ("No dai han", "4.000.000.000 VND", "long_term_debt"),
            ("Tong no phai tra", "12.000.000.000 VND", "total_liabilities"),
            ("Von chu so huu", "23.000.000.000 VND", "total_equity"),
            ("Tong nguon von", "35.000.000.000 VND", "total_capital_source"),
            ("Loi nhuan sau thue", "4.200.000.000 VND", "net_profit_after_tax"),
            ("Gia von hang ban", "26.000.000.000 VND", "cogs"),
            ("Dong tien tu hoat dong kinh doanh", "6.000.000.000 VND", "cf_operating"),
            ("Dong tien tu hoat dong dau tu", "-2.000.000.000 VND", "cf_investing"),
            ("Dong tien tu hoat dong tai chinh", "-3.000.000.000 VND", "cf_financing"),
            ("TSLD binh quan", "13.000.000.000 VND", "avg_current_assets"),
            ("Phai thu binh quan", "5.000.000.000 VND", "avg_accounts_receivable"),
            ("Ton kho binh quan", "3.000.000.000 VND", "avg_inventory"),
            ("Tong tai san binh quan", "30.000.000.000 VND", "avg_total_assets"),
            ("So nam so lieu tai chinh lien tuc", "4 nam", "historical_data_years"),
        ],
        "field_defs": {
            "revenue_2025": ({"amount_vnd": 40_000_000_000}, 0.97),
            "net_revenue": ({"amount_vnd": 40_000_000_000}, 0.97),
            "ebitda_2025": ({"amount_vnd": 5_500_000_000}, 0.95),
            "debt_service_annual": ({"amount_vnd": 2_800_000_000}, 0.94),
            "cash_and_equivalents": ({"amount_vnd": 6_000_000_000}, 0.95),
            "short_term_investments": ({"amount_vnd": 2_000_000_000}, 0.93),
            "accounts_receivable": ({"amount_vnd": 6_000_000_000}, 0.95),
            "inventory": ({"amount_vnd": 4_000_000_000}, 0.94),
            "current_assets_total": ({"amount_vnd": 18_000_000_000}, 0.95),
            "fixed_assets_and_ltd_investments": ({"amount_vnd": 17_000_000_000}, 0.93),
            "total_assets": ({"amount_vnd": 35_000_000_000}, 0.96),
            "current_liabilities": ({"amount_vnd": 8_000_000_000}, 0.95),
            "long_term_debt": ({"amount_vnd": 4_000_000_000}, 0.94),
            "total_liabilities": ({"amount_vnd": 12_000_000_000}, 0.95),
            "total_equity": ({"amount_vnd": 23_000_000_000}, 0.95),
            "total_capital_source": ({"amount_vnd": 35_000_000_000}, 0.95),
            "net_profit_after_tax": ({"amount_vnd": 4_200_000_000}, 0.95),
            "cogs": ({"amount_vnd": 26_000_000_000}, 0.94),
            "cf_operating": ({"amount_vnd": 6_000_000_000}, 0.93),
            "cf_investing": ({"amount_vnd": -2_000_000_000}, 0.9),
            "cf_financing": ({"amount_vnd": -3_000_000_000}, 0.9),
            "avg_current_assets": ({"amount_vnd": 13_000_000_000}, 0.9),
            "avg_accounts_receivable": ({"amount_vnd": 5_000_000_000}, 0.9),
            "avg_inventory": ({"amount_vnd": 3_000_000_000}, 0.9),
            "avg_total_assets": ({"amount_vnd": 30_000_000_000}, 0.9),
            "historical_data_years": ({"years": 4}, 0.9),
        },
    },
    {
        "key": "tax",
        "doc_type": "tax_filing",
        "filename": "to_khai_thue_2025.pdf",
        "title": "TO KHAI QUYET TOAN THUE TNDN 2025 - HOA SEN EXPORT",
        "lines": [("Doanh thu chiu thue", "39.200.000.000 VND", "revenue_2025_tax_filing")],
        "field_defs": {"revenue_2025_tax_filing": ({"amount_vnd": 39_200_000_000}, 0.96)},
    },
    {
        "key": "valuation",
        "doc_type": "valuation_certificate",
        "filename": "chung_thu_dinh_gia.pdf",
        "title": "CHUNG THU DINH GIA TAI SAN BAO DAM",
        "lines": [
            ("Gia tri dinh gia", "4.000.000.000 VND", "valuation_amount"),
            ("Ngay dinh gia", "2025-08-01", None),
            ("Hieu luc den", "2027-01-01", "valuation_expiry_date"),
        ],
        "field_defs": {
            "valuation_amount": ({"amount_vnd": 4_000_000_000}, 0.9),
            "valuation_expiry_date": ({"date": "2027-01-01"}, 0.9),
        },
    },
    {
        "key": "dkkd",
        "doc_type": "business_registration",
        "filename": "dang_ky_kinh_doanh.pdf",
        "title": "GIAY CHUNG NHAN DANG KY DOANH NGHIEP - HOA SEN EXPORT",
        "lines": [
            ("Le Thi Hoa", "55%", "ownership_structure"),
            ("Pham Van Sen", "45%", "ownership_structure"),
        ],
        "field_defs": {
            "ownership_structure": (
                {"owners": [{"name": "Le Thi Hoa", "pct": 55}, {"name": "Pham Van Sen", "pct": 45}]},
                0.93,
            )
        },
    },
    {
        "key": "bank",
        "doc_type": "bank_transactions",
        "filename": "giao_dich_ngan_hang.pdf",
        "title": "SAO KE GIAO DICH TAI KHOAN - HOA SEN EXPORT",
        "lines": [("Ty trong doanh thu tu khach hang lon nhat (Buyer X)", "30%", "top_customer_concentration")],
        "field_defs": {"top_customer_concentration": ({"buyer": "Buyer X", "pct": 30}, 0.85)},
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
                customer_id="CUST-HOASEN",
                product="SME_WC",
                requested_facility={
                    "amount_vnd": 3_000_000_000,
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

        # Collateral & Legal Agent domain — see seed_case_c06.py for the
        # full rationale. Clean ownership narrative (matches this case's
        # "clean approval" story, module docstring): no encumbrance, both
        # co-owners confirmed, checklist complete.
        session.add(
            CollateralRegistry(
                collateral_id=CASE_ID,
                owner_name="Le Thi Hoa",
                owner_id="CUST-HOASEN",
                registration_number="GCN-HS-2019-0112",
                registration_date=dt.datetime(2019, 3, 1, tzinfo=dt.timezone.utc),
                registration_authority="So Tai nguyen va Moi truong Long An",
                collateral_type="valuation_certificate",
            )
        )
        session.add(
            LegalDocumentStore(
                collateral_id=CASE_ID,
                doc_type="Giay chung nhan quyen su dung dat",
                issue_date=dt.datetime(2019, 3, 1, tzinfo=dt.timezone.utc),
                is_original=True,
                verification_status="VERIFIED",
            )
        )
        session.add(CoOwnerRegistry(collateral_id=CASE_ID, co_owner_id="Pham Van Sen", consent_status="CONFIRMED"))
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

    r = redis.from_url(REDIS_URL)
    try:
        r.lpush(ANALYZE_QUEUE, json.dumps({"case_id": CASE_ID}))
        print(f"enqueued analyze job for case {CASE_ID}")
    finally:
        r.close()


if __name__ == "__main__":
    main()
