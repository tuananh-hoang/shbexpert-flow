"""Seed Customer 360 & Credit History domain data for the 3 golden
customers (CUST-ANPHU/CUST-HOASEN/CUST-MINHLONG — C06/C07/C08).

Deliberately makes CUST-ANPHU's (C06) `cashflow_statement_summary` DIVERGE
from its BCTC-reported cf_operating (seeded in scripts/seed_case_c06.py:
+7.0B, net_cashflow=+2.0B) — the SHB transaction data here shows a
NEGATIVE net cashflow propped up by new borrowing, so
worker/app/agents/customer360.py::run_cashflow_check lands on OPPOSE while
worker/app/agents/financial.py::_cashflow_quality_finding (same issue_key
CASHFLOW_QUALITY) lands on SUPPORT — a real conflict for the detector to
find, same pattern as C06's existing COLLATERAL_COVERAGE conflict.
CUST-HOASEN/CUST-MINHLONG stay internally consistent (no manufactured
conflict) to keep their existing narratives (clean approval / weaker
fundamentals) intact.

`group_relationship`/`cross_guarantee` intentionally left empty for all 3 —
no related-party scenario seeded this pass (see plan's Rủi ro note); this
keeps run_related_parties_check's SUPPORT/LOW path exercised without
needing cross-referenced customer_ids that don't exist in tools-mock's
_OBLIGATIONS dict.

Run with: `docker compose exec api python -m scripts.seed_customer360_reference`
Idempotent — skips any row whose primary key already exists; for the
per-customer child tables (no natural single-row key), skips if that
customer already has any row in that table.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from shared.db import get_session
from shared.models import (
    CashflowStatementSummary,
    CreditLimit,
    CustomerMaster,
    LegalRepresentative,
    RelationshipHistory,
    ShareholderRegistry,
    TransactionAccount,
)


def _dt(y: int, m: int, d: int) -> dt.datetime:
    return dt.datetime(y, m, d, tzinfo=dt.timezone.utc)


CUSTOMERS = [
    {
        "customer_id": "CUST-ANPHU",
        "master": {"customer_name": "An Phu Packaging", "tax_code": "0301234567", "establish_date": _dt(2015, 1, 1), "industry_code": "C1702", "legal_rep_id": "REP-ANPHU-01"},
        "credit_limit": {"limit_type": "vay_ngan_han", "approved_amount": 6_000_000_000, "approval_date": _dt(2024, 1, 1), "expiry_date": _dt(2027, 1, 1), "approving_authority": "SHB HCM Branch"},
        "relationship": {"relationship_start_date": _dt(2019, 1, 1), "product_used": "SME_WC", "branch_id": "HCM-01"},
        "account": {"account_type": "CHECKING", "avg_balance": 3_000_000_000, "open_date": _dt(2019, 1, 1)},
        # Deliberately diverges from BCTC (+7.0B cf_operating) — see module docstring.
        "cashflow": {"period": "2025", "cf_operating": -2_000_000_000, "cf_investing": -1_000_000_000, "cf_financing": 1_500_000_000, "net_cashflow": -1_500_000_000},
        "shareholders": [("Nguyen Van A", 60), ("Tran Thi B", 25), ("Cong ty XYZ", 15)],
        "legal_rep": {"rep_name": "Nguyen Van A", "role": "Giam doc", "authorization_scope": "Toan quyen ky ket hop dong tin dung"},
    },
    {
        "customer_id": "CUST-HOASEN",
        "master": {"customer_name": "Hoa Sen Export", "tax_code": "0302345678", "establish_date": _dt(2012, 6, 1), "industry_code": "C1010", "legal_rep_id": "REP-HOASEN-01"},
        "credit_limit": {"limit_type": "vay_ngan_han", "approved_amount": 3_000_000_000, "approval_date": _dt(2023, 6, 1), "expiry_date": _dt(2027, 6, 1), "approving_authority": "SHB Long An Branch"},
        "relationship": {"relationship_start_date": _dt(2016, 1, 1), "product_used": "SME_WC", "branch_id": "LongAn-01"},
        "account": {"account_type": "CHECKING", "avg_balance": 2_500_000_000, "open_date": _dt(2016, 1, 1)},
        # Consistent with BCTC (+6.0B cf_operating, net +1.0B) — no manufactured conflict.
        "cashflow": {"period": "2025", "cf_operating": 5_500_000_000, "cf_investing": -2_000_000_000, "cf_financing": -2_500_000_000, "net_cashflow": 1_000_000_000},
        "shareholders": [("Le Thi Hoa", 55), ("Pham Van Sen", 45)],
        "legal_rep": {"rep_name": "Le Thi Hoa", "role": "Giam doc", "authorization_scope": "Toan quyen ky ket hop dong tin dung"},
    },
    {
        "customer_id": "CUST-MINHLONG",
        "master": {"customer_name": "Minh Long Trading", "tax_code": "0303456789", "establish_date": _dt(2018, 3, 1), "industry_code": "G4661", "legal_rep_id": "REP-MINHLONG-01"},
        # approved_amount == existing obligations (4.2B loan + 0.8B LC, tools-mock/_OBLIGATIONS)
        # -> 100% utilization, intentional: matches this case's "weaker fundamentals" narrative.
        "credit_limit": {"limit_type": "vay_ngan_han", "approved_amount": 5_000_000_000, "approval_date": _dt(2022, 1, 1), "expiry_date": _dt(2026, 1, 1), "approving_authority": "SHB Binh Duong Branch"},
        "relationship": {"relationship_start_date": _dt(2022, 1, 1), "product_used": "SME_WC", "branch_id": "BinhDuong-01"},
        "account": {"account_type": "CHECKING", "avg_balance": 800_000_000, "open_date": _dt(2022, 1, 1)},
        # Consistent with BCTC (+0.8B cf_operating, net +1.5B, financing-assisted but not manufactured conflict).
        "cashflow": {"period": "2025", "cf_operating": 700_000_000, "cf_investing": -400_000_000, "cf_financing": 1_000_000_000, "net_cashflow": 1_300_000_000},
        "shareholders": [("Vu Minh Long", 70), ("Dang Thi Lan", 30)],
        "legal_rep": {"rep_name": "Vu Minh Long", "role": "Giam doc", "authorization_scope": "Toan quyen ky ket hop dong tin dung"},
    },
]


def main() -> None:
    with get_session() as session:
        for cust in CUSTOMERS:
            cid = cust["customer_id"]

            if session.get(CustomerMaster, cid) is None:
                session.add(CustomerMaster(customer_id=cid, **cust["master"]))
            else:
                print(f"customer_master already exists for {cid} — skipping")

            if not session.execute(select(CreditLimit).where(CreditLimit.customer_id == cid)).scalars().first():
                session.add(CreditLimit(customer_id=cid, **cust["credit_limit"]))

            if not session.execute(select(RelationshipHistory).where(RelationshipHistory.customer_id == cid)).scalars().first():
                session.add(RelationshipHistory(customer_id=cid, **cust["relationship"]))

            if not session.execute(select(TransactionAccount).where(TransactionAccount.customer_id == cid)).scalars().first():
                session.add(TransactionAccount(customer_id=cid, **cust["account"]))

            if not session.execute(select(CashflowStatementSummary).where(CashflowStatementSummary.customer_id == cid)).scalars().first():
                session.add(CashflowStatementSummary(customer_id=cid, **cust["cashflow"]))

            if not session.execute(select(ShareholderRegistry).where(ShareholderRegistry.customer_id == cid)).scalars().first():
                for name, pct in cust["shareholders"]:
                    session.add(ShareholderRegistry(customer_id=cid, shareholder_name=name, ownership_pct=pct))

            if not session.execute(select(LegalRepresentative).where(LegalRepresentative.customer_id == cid)).scalars().first():
                session.add(LegalRepresentative(customer_id=cid, **cust["legal_rep"]))

            print(f"seeded customer360 domain rows for {cid}")


if __name__ == "__main__":
    main()
