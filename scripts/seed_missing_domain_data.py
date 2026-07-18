"""Seed per-case domain data that was missing because the case-existence guard
in seed_case_c0*.py / seed_synthetic_cases.py bailed early (cases already
existed from a prior partial run) before the associated domain rows were
written.

Specifically seeds:
  C06 / C07 / C08: CollateralRegistry, LegalDocumentStore, CoOwnerRegistry,
                   ChecklistCompletion
  CASE-CUS-0000N:  CustomerMaster, LegalRepresentative, CollateralRegistry,
                   ChecklistCompletion, CashflowStatementSummary

Idempotent — skips any row whose primary key (or natural unique check) already
exists.  Run with:
  docker compose exec api python -m scripts.seed_missing_domain_data
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

from sqlalchemy import select

from shared.db import get_session
from shared.models import (
    CashflowStatementSummary,
    ChecklistCompletion,
    CollateralRegistry,
    CoOwnerRegistry,
    CustomerMaster,
    LegalDocumentStore,
    LegalRepresentative,
)

CASES_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "cases"
_VALUATION_VALIDITY_DAYS = 365
_SHB_CASHFLOW_FACTOR = 0.92
CHECKLIST_IDS = ("LC-VALUATION-EXPIRY-60D", "LC-VALUATION-APPRAISER-LICENSE")


def _seed_if_missing(session, model, pk_attr, pk_val, **kwargs):
    if session.get(model, pk_val) is None:
        session.add(model(**{pk_attr: pk_val}, **kwargs))
        return True
    return False


def _checklist_missing(session, collateral_id):
    return not session.execute(
        select(ChecklistCompletion).where(ChecklistCompletion.collateral_id == collateral_id)
    ).scalars().first()


def seed_c06(session) -> None:
    cid = "C06"
    if session.get(CollateralRegistry, cid) is not None:
        print(f"CollateralRegistry for {cid} already exists — skipping")
    else:
        session.add(CollateralRegistry(
            collateral_id=cid,
            owner_name="Nguyen Van A",
            owner_id="CUST-ANPHU",
            registration_number="GCN-AP-2020-0456",
            registration_date=datetime(2020, 1, 15, tzinfo=timezone.utc),
            registration_authority="So Tai nguyen va Moi truong TP.HCM",
            collateral_type="valuation_certificate",
        ))
        session.add(LegalDocumentStore(
            collateral_id=cid,
            doc_type="Giay chung nhan quyen su dung dat",
            issue_date=datetime(2020, 1, 15, tzinfo=timezone.utc),
            is_original=True,
            verification_status="VERIFIED",
        ))
        for co_owner in ("Tran Thi B", "Cong ty XYZ"):
            session.add(CoOwnerRegistry(collateral_id=cid, co_owner_id=co_owner, consent_status="CONFIRMED"))
        print(f"seeded CollateralRegistry + legal docs for {cid}")

    if _checklist_missing(session, cid):
        for checklist_id in CHECKLIST_IDS:
            session.add(ChecklistCompletion(
                collateral_id=cid, checklist_id=checklist_id,
                completion_status="completed",
                completed_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
                responsible_party="rm1",
            ))
        print(f"seeded ChecklistCompletion for {cid}")


def seed_c07(session) -> None:
    cid = "C07"
    if session.get(CollateralRegistry, cid) is not None:
        print(f"CollateralRegistry for {cid} already exists — skipping")
    else:
        session.add(CollateralRegistry(
            collateral_id=cid,
            owner_name="Le Thi Hoa",
            owner_id="CUST-HOASEN",
            registration_number="GCN-HS-2019-0112",
            registration_date=datetime(2019, 3, 1, tzinfo=timezone.utc),
            registration_authority="So Tai nguyen va Moi truong Long An",
            collateral_type="valuation_certificate",
        ))
        session.add(LegalDocumentStore(
            collateral_id=cid,
            doc_type="Giay chung nhan quyen su dung dat",
            issue_date=datetime(2019, 3, 1, tzinfo=timezone.utc),
            is_original=True,
            verification_status="VERIFIED",
        ))
        session.add(CoOwnerRegistry(collateral_id=cid, co_owner_id="Pham Van Sen", consent_status="CONFIRMED"))
        print(f"seeded CollateralRegistry + legal docs for {cid}")

    if _checklist_missing(session, cid):
        for checklist_id in CHECKLIST_IDS:
            session.add(ChecklistCompletion(
                collateral_id=cid, checklist_id=checklist_id,
                completion_status="completed",
                completed_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
                responsible_party="rm1",
            ))
        print(f"seeded ChecklistCompletion for {cid}")


def seed_c08(session) -> None:
    cid = "C08"
    if session.get(CollateralRegistry, cid) is not None:
        print(f"CollateralRegistry for {cid} already exists — skipping")
    else:
        session.add(CollateralRegistry(
            collateral_id=cid,
            owner_name="Vu Minh Long",
            owner_id="CUST-MINHLONG",
            registration_number="GCN-ML-2018-0789",
            registration_date=datetime(2018, 6, 1, tzinfo=timezone.utc),
            registration_authority="So Tai nguyen va Moi truong Binh Duong",
            collateral_type="valuation_certificate",
        ))
        session.add(LegalDocumentStore(
            collateral_id=cid,
            doc_type="Giay chung nhan quyen su dung dat",
            issue_date=datetime(2018, 6, 1, tzinfo=timezone.utc),
            is_original=True,
            verification_status="VERIFIED",
        ))
        session.add(CoOwnerRegistry(collateral_id=cid, co_owner_id="Dang Thi Lan", consent_status="CONFIRMED"))
        print(f"seeded CollateralRegistry + legal docs for {cid}")

    if _checklist_missing(session, cid):
        for checklist_id in CHECKLIST_IDS:
            session.add(ChecklistCompletion(
                collateral_id=cid, checklist_id=checklist_id,
                completion_status="completed",
                completed_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                responsible_party="rm1",
            ))
        print(f"seeded ChecklistCompletion for {cid}")


def seed_synthetic(session) -> None:
    for i in range(1, 5):
        case_id = f"CASE-CUS-0000{i}"
        path = CASES_DIR / case_id / "case.json"
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        customer = raw["customer"]
        cust_id = customer["customer_id"]
        col = raw["collateral"][0]
        fin2025 = next(x for x in raw["financials"] if x["period"] == "2025")

        if session.get(CustomerMaster, cust_id) is None:
            session.add(CustomerMaster(
                customer_id=cust_id,
                customer_name=customer["legal_name"],
                tax_code=customer["mock_tax_id"],
                establish_date=datetime.fromisoformat(customer["incorporation_date"]).replace(tzinfo=timezone.utc),
                industry_code=customer["industry_code"],
                legal_rep_id=customer["representative_party_id"],
            ))
            session.add(LegalRepresentative(
                customer_id=cust_id,
                rep_id=customer["representative_party_id"],
                rep_name=f"Nguoi dai dien phap luat cua {customer['legal_name']}",
                role="LEGAL_REPRESENTATIVE",
                authorization_scope="TOAN_QUYEN",
            ))
            print(f"seeded CustomerMaster + LegalRepresentative for {cust_id}")
        else:
            print(f"CustomerMaster for {cust_id} already exists — skipping")

        if session.get(CollateralRegistry, case_id) is None:
            session.add(CollateralRegistry(
                collateral_id=case_id,
                owner_name=customer["legal_name"],
                owner_id=cust_id,
                registration_number=col.get("ownership_document_id"),
                collateral_type="real_estate",
            ))
            print(f"seeded CollateralRegistry for {case_id}")

        if _checklist_missing(session, case_id):
            for checklist_id in CHECKLIST_IDS:
                session.add(ChecklistCompletion(
                    collateral_id=case_id, checklist_id=checklist_id,
                    completion_status="completed",
                    completed_date=datetime.now(timezone.utc),
                    responsible_party="rm1",
                ))
            print(f"seeded ChecklistCompletion for {case_id}")

        if not session.execute(
            select(CashflowStatementSummary).where(CashflowStatementSummary.customer_id == cust_id)
        ).scalars().first():
            cf_op = round(fin2025["operating_cash_flow"] * _SHB_CASHFLOW_FACTOR)
            cf_inv = round(fin2025["investing_cash_flow"] * _SHB_CASHFLOW_FACTOR)
            cf_fin = round(fin2025["financing_cash_flow"] * _SHB_CASHFLOW_FACTOR)
            session.add(CashflowStatementSummary(
                customer_id=cust_id,
                period="2025",
                cf_operating=cf_op,
                cf_investing=cf_inv,
                cf_financing=cf_fin,
                net_cashflow=cf_op + cf_inv + cf_fin,
            ))
            print(f"seeded CashflowStatementSummary for {cust_id}")


def main() -> None:
    with get_session() as session:
        seed_c06(session)
        seed_c07(session)
        seed_c08(session)
        seed_synthetic(session)
    print("done — all missing domain data seeded")


if __name__ == "__main__":
    main()
