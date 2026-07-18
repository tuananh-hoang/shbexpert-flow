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

Also seeds the identity/collateral-ownership rows the Customer 360 and
Collateral & Legal agents' tools read from directly (customer_master,
legal_representative, collateral_registry) — added after discovering these
4 cases' analyze jobs were crashing outright on tool 404s because this
script predates those agents and never wrote them:
  - customer_master        <- customer.legal_name/mock_tax_id/
                                industry_code/incorporation_date/
                                representative_party_id (direct)
  - legal_representative    : rep_name has no source field (case.json
                                only has a party ID, no person name) — a
                                placeholder derived from legal_name, same
                                "clearly synthetic, not fabricated-real"
                                spirit as everything else in this script
  - collateral_registry.owner_id <- customer.customer_id (matches
                                Case.customer_id, same convention
                                scripts/seed_case_c06.py uses, so
                                validate_ownership's ownership_verified
                                comes back True — case.json's own
                                encumbrance_status=NONE agrees)
Deliberately NOT seeded: credit_obligations/CIC records — those live in
tools-mock (external system), not this DB; see tools-mock/app/main.py's
_OBLIGATIONS/_CIC_RECORDS for the matching CUS-00001..4 entries.

Also seeds cashflow_statement_summary — its absence wasn't just a missing-
field gap, it crashed the whole job one node later than the tool-404s
above: worker/app/agents/customer360.py::run_cashflow_check's "no data"
branch (summary is None) legitimately writes evidence_ids=[] (there's
nothing to cite), which is correct — but the synthesize node's NFR-01
check rejects ANY DecisionPackage-referenced finding with empty
evidence_ids, so `job_completed` never fired even after Việc 1's fan-out
isolation fix (that fix only covers agent EXCEPTIONS, not a legitimately-
empty-evidence finding produced by a fully-successful agent). Seeding real
values here — instead of hardening the NFR-01 check — keeps this the same
"missing data" root cause as the rest of this script, and avoids weakening
a real traceability guardrail. cf_operating/investing/financing derived
from each case's financials[2025] BCTC-reported cashflow, scaled by 0.92
so SHB's own transaction view deliberately differs from the customer-
submitted figure — same "official vs submitted" convention as
tools-mock/app/main.py::_valuation_record.

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import redis

from shared.db import get_session
from shared.models import (
    CashflowStatementSummary,
    Case,
    ChecklistCompletion,
    CollateralRegistry,
    CustomerMaster,
    Document,
    ExtractedField,
    LegalRepresentative,
)
from shared.queue import ANALYZE_QUEUE
from shared.storage import upload_bytes

from scripts.pdf_utils import render_document_pdf

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CASES_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "cases"
CASE_IDS = ["CASE-CUS-00001", "CASE-CUS-00002", "CASE-CUS-00003", "CASE-CUS-00004"]

_DEBT_AMORTIZATION_YEARS = 5
_VALUATION_VALIDITY_DAYS = 365
_SHB_CASHFLOW_FACTOR = 0.92


def _fmt_vnd(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".") + " VND"


def _load_case(case_id: str) -> dict:
    path = CASES_DIR / case_id / "case.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_docs(raw: dict) -> list[dict]:
    customer = raw["customer"]
    fin2025 = next(x for x in raw["financials"] if x["period"] == "2025")
    fin2024 = next(x for x in raw["financials"] if x["period"] == "2024")
    col = raw["collateral"][0]
    bizreg = next(x for x in raw["legal_documents"] if x["document_type"] == "BUSINESS_REGISTRATION")

    ebitda = fin2025["profit_before_tax"] + fin2025["interest_expense"]
    debt_service = fin2025["interest_expense"] + fin2025["debt"] / _DEBT_AMORTIZATION_YEARS
    tax_filing_revenue = fin2025.get("reported_revenue", fin2025["revenue"])
    valuation_expiry = (
        date.fromisoformat(col["valuation_date"]) + timedelta(days=_VALUATION_VALIDITY_DAYS)
    ).isoformat()

    # Standard financial-statement ratio fields (shared/constants.py::
    # REQUIRED_STATEMENT_FIELDS + financial.py::_STATEMENT_AMOUNT_FIELDS) —
    # added after discovering these 4 cases' BCTC document only ever carried
    # the 3 DSCR-only fields above, so run_financial_agent's
    # _missing_required_statement_fields ALWAYS returned non-empty, forcing
    # the NEED_DATA fallback finding — whose evidence_ids were themselves
    # empty (no REQUIRED_STATEMENT_FIELDS present to cite), which crashed
    # the whole job at synthesize's NFR-01 check. Mapped directly from
    # case.json's financials[] block (balance sheet already balances:
    # assets = current_assets_total + fixed_assets_and_ltd_investments,
    # liabilities = current_liabilities(payables) + long_term_debt(debt)) —
    # only short_term_investments has no source field, left at 0 rather
    # than fabricated. avg_* fields use the (2024 + 2025) two-point average,
    # same convention scripts/seed_case_c06.py's fixed mock figures assume.
    current_assets_total = fin2025["assets"] - fin2025["fixed_assets"]
    avg_current_assets = ((fin2024["assets"] - fin2024["fixed_assets"]) + current_assets_total) / 2
    avg_accounts_receivable = (fin2024["receivables"] + fin2025["receivables"]) / 2
    avg_inventory = (fin2024["inventory"] + fin2025["inventory"]) / 2
    avg_total_assets = (fin2024["assets"] + fin2025["assets"]) / 2

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
                ("Doanh thu thuan (dung cho phan tich ty so BCTC)", _fmt_vnd(fin2025["revenue"]), "net_revenue"),
                ("Tien va tuong duong tien", _fmt_vnd(fin2025["cash"]), "cash_and_equivalents"),
                ("Dau tu ngan han (khong co du lieu nguon, gia dinh = 0)", _fmt_vnd(0), "short_term_investments"),
                ("Phai thu khach hang", _fmt_vnd(fin2025["receivables"]), "accounts_receivable"),
                ("Hang ton kho", _fmt_vnd(fin2025["inventory"]), "inventory"),
                ("Tong tai san luu dong", _fmt_vnd(current_assets_total), "current_assets_total"),
                ("Tai san co dinh va dau tu dai han", _fmt_vnd(fin2025["fixed_assets"]), "fixed_assets_and_ltd_investments"),
                ("Tong tai san", _fmt_vnd(fin2025["assets"]), "total_assets"),
                ("No ngan han", _fmt_vnd(fin2025["payables"]), "current_liabilities"),
                ("No dai han", _fmt_vnd(fin2025["debt"]), "long_term_debt"),
                ("Tong no phai tra", _fmt_vnd(fin2025["liabilities"]), "total_liabilities"),
                ("Von chu so huu", _fmt_vnd(fin2025["equity"]), "total_equity"),
                ("Tong nguon von", _fmt_vnd(fin2025["liabilities"] + fin2025["equity"]), "total_capital_source"),
                ("Loi nhuan sau thue", _fmt_vnd(fin2025["net_profit"]), "net_profit_after_tax"),
                ("Gia von hang ban", _fmt_vnd(fin2025["cogs"]), "cogs"),
                ("Dong tien tu hoat dong kinh doanh", _fmt_vnd(fin2025["operating_cash_flow"]), "cf_operating"),
                ("Dong tien tu hoat dong dau tu", _fmt_vnd(fin2025["investing_cash_flow"]), "cf_investing"),
                ("Dong tien tu hoat dong tai chinh", _fmt_vnd(fin2025["financing_cash_flow"]), "cf_financing"),
                ("TSLD binh quan", _fmt_vnd(avg_current_assets), "avg_current_assets"),
                ("Phai thu binh quan", _fmt_vnd(avg_accounts_receivable), "avg_accounts_receivable"),
                ("Ton kho binh quan", _fmt_vnd(avg_inventory), "avg_inventory"),
                ("Tong tai san binh quan", _fmt_vnd(avg_total_assets), "avg_total_assets"),
                ("So nam so lieu tai chinh lien tuc", "3 nam", "historical_data_years"),
            ],
            "field_defs": {
                "revenue_2025": ({"amount_vnd": fin2025["revenue"]}, 0.97),
                "ebitda_2025": ({"amount_vnd": round(ebitda)}, 0.6),
                "debt_service_annual": ({"amount_vnd": round(debt_service)}, 0.6),
                "net_revenue": ({"amount_vnd": fin2025["revenue"]}, 0.97),
                "cash_and_equivalents": ({"amount_vnd": fin2025["cash"]}, 0.95),
                "short_term_investments": ({"amount_vnd": 0}, 0.93),
                "accounts_receivable": ({"amount_vnd": fin2025["receivables"]}, 0.95),
                "inventory": ({"amount_vnd": fin2025["inventory"]}, 0.94),
                "current_assets_total": ({"amount_vnd": round(current_assets_total)}, 0.95),
                "fixed_assets_and_ltd_investments": ({"amount_vnd": fin2025["fixed_assets"]}, 0.93),
                "total_assets": ({"amount_vnd": fin2025["assets"]}, 0.96),
                "current_liabilities": ({"amount_vnd": fin2025["payables"]}, 0.95),
                "long_term_debt": ({"amount_vnd": fin2025["debt"]}, 0.94),
                "total_liabilities": ({"amount_vnd": fin2025["liabilities"]}, 0.95),
                "total_equity": ({"amount_vnd": fin2025["equity"]}, 0.95),
                "total_capital_source": ({"amount_vnd": fin2025["liabilities"] + fin2025["equity"]}, 0.95),
                "net_profit_after_tax": ({"amount_vnd": fin2025["net_profit"]}, 0.95),
                "cogs": ({"amount_vnd": fin2025["cogs"]}, 0.94),
                "cf_operating": ({"amount_vnd": fin2025["operating_cash_flow"]}, 0.93),
                "cf_investing": ({"amount_vnd": fin2025["investing_cash_flow"]}, 0.9),
                "cf_financing": ({"amount_vnd": fin2025["financing_cash_flow"]}, 0.9),
                "avg_current_assets": ({"amount_vnd": round(avg_current_assets)}, 0.9),
                "avg_accounts_receivable": ({"amount_vnd": round(avg_accounts_receivable)}, 0.9),
                "avg_inventory": ({"amount_vnd": round(avg_inventory)}, 0.9),
                "avg_total_assets": ({"amount_vnd": round(avg_total_assets)}, 0.9),
                "historical_data_years": ({"years": 3}, 0.9),
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

        customer = raw["customer"]
        col = raw["collateral"][0]
        session.add(
            CustomerMaster(
                customer_id=customer["customer_id"],
                customer_name=customer["legal_name"],
                tax_code=customer["mock_tax_id"],
                establish_date=datetime.fromisoformat(customer["incorporation_date"]).replace(tzinfo=timezone.utc),
                industry_code=customer["industry_code"],
                legal_rep_id=customer["representative_party_id"],
            )
        )
        session.add(
            LegalRepresentative(
                customer_id=customer["customer_id"],
                rep_id=customer["representative_party_id"],
                rep_name=f"Nguoi dai dien phap luat cua {customer['legal_name']}",
                role="LEGAL_REPRESENTATIVE",
                authorization_scope="TOAN_QUYEN",
            )
        )
        session.add(
            CollateralRegistry(
                collateral_id=case_id,
                owner_name=customer["legal_name"],
                owner_id=customer["customer_id"],
                registration_number=col.get("ownership_document_id"),
                collateral_type="real_estate",
            )
        )
        # legal_checklist_template's 2 valuation_certificate items are a
        # global template (already seeded once, shared across all cases) —
        # only checklist_completion (per-case) was ever missing for these 4,
        # which left run_legal_checklist_check's grounded_evidence_ids
        # empty (no completion_id to cite) even though it had real Qdrant
        # citations, tripping the same NFR-01 check. Marked "completed" for
        # both mandatory items, same as scripts/seed_case_c06.py's precedent
        # — encumbrance_status is NONE for all 4 synthetic collaterals, so
        # there's no missing-checklist story being tested here.
        for checklist_id in ("LC-VALUATION-EXPIRY-60D", "LC-VALUATION-APPRAISER-LICENSE"):
            session.add(
                ChecklistCompletion(
                    collateral_id=case_id,
                    checklist_id=checklist_id,
                    completion_status="completed",
                    completed_date=datetime.now(timezone.utc),
                    responsible_party="rm1",
                )
            )

        fin2025 = next(x for x in raw["financials"] if x["period"] == "2025")
        cf_operating = round(fin2025["operating_cash_flow"] * _SHB_CASHFLOW_FACTOR)
        cf_investing = round(fin2025["investing_cash_flow"] * _SHB_CASHFLOW_FACTOR)
        cf_financing = round(fin2025["financing_cash_flow"] * _SHB_CASHFLOW_FACTOR)
        session.add(
            CashflowStatementSummary(
                customer_id=customer["customer_id"],
                period="2025",
                cf_operating=cf_operating,
                cf_investing=cf_investing,
                cf_financing=cf_financing,
                net_cashflow=cf_operating + cf_investing + cf_financing,
            )
        )

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
