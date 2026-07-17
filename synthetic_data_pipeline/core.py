from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Any

from openpyxl import Workbook

INDUSTRIES = [
    ("C101", "San xuat thuc pham"), ("C141", "May mac"),
    ("C162", "Che bien go"), ("F410", "Xay dung"),
    ("G461", "Ban buon"), ("G471", "Ban le"),
    ("H493", "Van tai"), ("I551", "Luu tru"),
    ("J620", "Lap trinh"), ("M702", "Tu van"),
    ("N782", "Cung ung lao dong"), ("C201", "Hoa chat"),
]
POLICY_FAMILIES = ["PRODUCT_ELIGIBILITY", "DOCUMENT_COMPLETENESS", "PURPOSE_HARD_GATES", "FINANCIAL_ASSESSMENT", "COLLATERAL_VALUATION", "CIC_KYC_AML_ROUTING"]
LEGAL_TYPES = ["BUSINESS_REGISTRATION", "CHARTER", "APPOINTMENT_DECISION", "MOCK_REPRESENTATIVE_ID", "LOAN_RESOLUTION"]


@dataclass(frozen=True)
class PipelineConfig:
    customer_count: int = 120
    seed: int = 20260718
    as_of_date: date = date(2026, 6, 30)


def _id(prefix: str, n: int) -> str:
    return f"{prefix}-{n:05d}"


def _money(x: float) -> int:
    return int(round(x / 1000) * 1000)


def build_master_data(config: PipelineConfig = PipelineConfig()) -> dict[str, Any]:
    """Build the clean, authoritative master pools before any case is assembled."""
    rng = Random(config.seed)
    industry = [
        {"industry_code": code, "industry_version": "VSIC-2025", "industry_name": name,
         "period": f"{2024 + q // 4}-Q{q % 4 + 1}", "growth_rate": round(.02 + ((i + q) % 12) / 100, 3),
         "benchmark_net_margin": round(.04 + ((i + q) % 7) / 100, 3), "risk_level": ["LOW", "MEDIUM", "HIGH"][i % 3],
         "seasonality_index": round(.82 + ((i + q) % 5) * .09, 2), "source_type": "synthetic_benchmark", "synthetic_estimate": True}
        for i, (code, name) in enumerate(INDUSTRIES, 1) for q in range(8)
    ]
    policies = [
        {"policy_id": f"MOCK-{family}-V{v}", "policy_family": family, "version": v,
         "effective_from": f"202{3 + v}-01-01", "effective_to": None if v == 3 else f"202{4 + v}-01-01",
         "applicable_products": ["SME_WORKING_CAPITAL"], "rules": [f"{family}-R1-V{v}"],
         "hard_stops": ["PROHIBITED_PURPOSE"] if family == "PURPOSE_HARD_GATES" else [],
         "change_set": ["HAIRCUT_30_TO_35"] if family == "COLLATERAL_VALUATION" and v == 3 else [], "synthetic_flag": True}
        for family in POLICY_FAMILIES for v in range(1, 4)
    ]
    customers: list[dict[str, Any]] = []
    parties: list[dict[str, Any]] = []
    applications: list[dict[str, Any]] = []
    financials: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    legal_documents: list[dict[str, Any]] = []
    collateral: list[dict[str, Any]] = []
    cic_reports: list[dict[str, Any]] = []
    kyc_screenings: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for n in range(1, config.customer_count + 1):
        cid, appid, repid, relid = _id("CUS", n), _id("APP", n), _id("PTY", n * 10), _id("PTY", n * 10 + 1)
        code, sector = INDUSTRIES[(n - 1) % len(INDUSTRIES)]
        customer = {"customer_id": cid, "legal_name": f"CONG TY TNHH MOCK {sector.upper()} {n:03d}",
                    "mock_tax_id": f"MOCK-TAX-{config.seed % 10000:04d}-{n:05d}", "industry_code": code,
                    "industry_version": "VSIC-2025", "incorporation_date": str(date(2012 + n % 11, n % 12 + 1, n % 27 + 1)),
                    "legal_address": f"So {100+n} Duong Mock {n % 20 + 1}, Ha Noi", "representative_party_id": repid,
                    "related_party_ids": [relid], "as_of_date": str(config.as_of_date), "synthetic_flag": True}
        customers.append(customer)
        parties += [{"party_id": repid, "party_name": f"NGUOI DAI DIEN MOCK {n:03d}", "party_role": "LEGAL_REPRESENTATIVE", "synthetic_flag": True},
                    {"party_id": relid, "party_name": f"BEN LIEN QUAN MOCK {n:03d}", "party_role": "RELATED_PARTY", "synthetic_flag": True}]
        amount = _money(rng.randint(2_000_000_000, 14_000_000_000))
        applications.append({"application_id": appid, "customer_id": cid, "product_code": "SME_WORKING_CAPITAL", "requested_amount": amount,
                             "currency": "VND", "tenor_months": [6, 9, 12][n % 3], "purpose_code": "WORKING_CAPITAL",
                             "repayment_method": "MONTHLY_INTEREST_QUARTERLY_PRINCIPAL", "repayment_source": "OPERATING_CASH_FLOW",
                             "proposed_collateral_ids": [_id("COL", n)], "submitted_at": str(config.as_of_date - timedelta(days=n % 45)),
                             "policy_snapshot_id": "MOCK-POLICY-PACK-V3", "synthetic_flag": True})
        for k, typ in enumerate(LEGAL_TYPES, 1):
            legal_documents.append({"document_id": f"DOC-{n:05d}-{k}", "customer_id": cid, "application_id": appid, "document_type": typ,
                                    "document_number": f"MOCK-{typ[:3]}-{n:05d}", "issued_at": str(config.as_of_date - timedelta(days=200+k)),
                                    "valid_to": str(config.as_of_date + timedelta(days=365)) if typ == "MOCK_REPRESENTATIVE_ID" else None,
                                    "canonical_fields": {"legal_name": customer["legal_name"], "mock_tax_id": customer["mock_tax_id"]}, "synthetic_flag": True})
        for pidx, period in enumerate(["2023", "2024", "2025", "2026-H1"]):
            revenue = _money(rng.randint(8_000_000_000, 72_000_000_000) * (.78 if period == "2026-H1" else .84 + .07 * pidx))
            cogs, opex, interest = _money(revenue * .64), _money(revenue * .17), _money(amount * .08)
            pbt, tax, np = revenue - cogs - opex - interest, 0, 0
            tax, np = max(0, _money(pbt * .2)), pbt - max(0, _money(pbt * .2))
            cash, receivable, inventory, fixed = _money(revenue * .1), _money(revenue * .18), _money(revenue * .12), _money(revenue * .22)
            assets, payables, debt = cash + receivable + inventory + fixed, _money(revenue * .1), _money(amount * .55)
            opcf, invcf, fincf = _money(np + revenue * .04), _money(-revenue * .03), _money(revenue * .01)
            netcf = opcf + invcf + fincf
            financials.append({"financial_id": f"FIN-{cid}-{period}", "customer_id": cid, "period": period, "revenue": revenue, "cogs": cogs,
                               "gross_profit": revenue-cogs, "operating_expenses": opex, "interest_expense": interest, "profit_before_tax": pbt,
                               "tax": tax, "net_profit": np, "cash": cash, "receivables": receivable, "inventory": inventory, "fixed_assets": fixed,
                               "assets": assets, "payables": payables, "debt": debt, "liabilities": payables+debt, "equity": assets-payables-debt,
                               "opening_cash": cash-netcf, "operating_cash_flow": opcf, "investing_cash_flow": invcf, "financing_cash_flow": fincf,
                               "net_cash_flow": netcf, "ending_cash": cash, "formula_version": "FIN-0.1", "synthetic_flag": True})
        latest = financials[-1]
        balance, txn_count, account_id = latest["opening_cash"], 50 + (n * 17) % 151, _id("ACC", n)
        for t in range(1, txn_count):
            direction, value = ("IN" if t % 3 else "OUT"), _money(rng.randint(5_000_000, 160_000_000))
            balance += value if direction == "IN" else -value
            transactions.append({"transaction_id": f"TXN-{n:05d}-{t:04d}", "account_id": account_id, "customer_id": cid,
                                 "booking_date": str(config.as_of_date-timedelta(days=txn_count-t)), "direction": direction, "amount": value, "currency": "VND",
                                 "counterparty_id": _id("CP", (n*7+t)%400+1), "counterparty_name": f"DOI TAC MOCK {(n*7+t)%400+1:03d}",
                                 "category": "SALES_RECEIPT" if direction == "IN" else "OPERATING_PAYMENT", "running_balance": balance, "synthetic_flag": True})
        diff = latest["ending_cash"] - balance
        transactions.append({"transaction_id": f"TXN-{n:05d}-{txn_count:04d}", "account_id": account_id, "customer_id": cid, "booking_date": str(config.as_of_date),
                             "direction": "IN" if diff >= 0 else "OUT", "amount": abs(diff), "currency": "VND", "counterparty_id": "CP-SETTLEMENT",
                             "counterparty_name": "DOI TAC MOCK SETTLEMENT", "category": "SETTLEMENT_ADJUSTMENT", "running_balance": latest["ending_cash"], "synthetic_flag": True})
        valuation = _money(amount * (1.7 + (n % 4) * .1))
        collateral.append({"collateral_id": _id("COL", n), "application_id": appid, "owner_party_id": repid, "property_type": "RESIDENTIAL_REAL_ESTATE",
                           "mock_address": f"Can {n%50+1}, Toa nha Mock {n:03d}, Ha Noi", "valuation_amount": valuation,
                           "valuation_date": str(config.as_of_date-timedelta(days=20+n%120)), "haircut_rate": .35,
                           "eligible_value": _money(valuation*.65), "encumbrance_status": "NONE", "encumbrance_amount": 0,
                           "ownership_document_id": f"DOC-{n:05d}-1", "synthetic_flag": True})
        exposure = _money(amount * (.2 + (n % 4)*.05))
        cic_reports.append({"cic_report_id": _id("CIC", n), "customer_id": cid, "checked_at": str(config.as_of_date-timedelta(days=n%7)),
                            "facilities": [{"facility_id": f"CICF-{n:05d}-1", "mock_lender_code": f"MOCK_BANK_{n%8+1:02d}", "current_outstanding": exposure,
                                            "debt_group": 1, "days_past_due": 0, "delinquency_history": []}], "inquiry_count_30d": n%3, "inquiry_count_12m": 1+n%7, "synthetic_flag": True})
        for pid in [repid, relid]:
            kyc_screenings.append({"screening_id": f"KYC-{pid}", "party_id": pid, "customer_id": cid, "checked_at": str(config.as_of_date),
                                   "screening_list_id": "MOCK-WATCHLIST-V1", "match_status": "NO_MATCH", "match_score": 0.0,
                                   "matched_mock_entity_id": None, "analyst_status": "CLEARED", "synthetic_flag": True})
        customer_txs = [row for row in transactions if row["customer_id"] == cid]
        relationships.append({"relationship_id": _id("REL", n), "customer_id": cid, "account_id": account_id, "account_balance": customer_txs[-1]["running_balance"],
                              "current_exposure": exposure, "turnover_in": sum(t["amount"] for t in customer_txs if t["direction"] == "IN"),
                              "turnover_out": sum(t["amount"] for t in customer_txs if t["direction"] == "OUT"), "past_due": 0,
                              "products": ["MOCK_CURRENT_ACCOUNT"], "rm_note": "Khach hang mock co giao dich on dinh.", "synthetic_flag": True})
    return {"manifest": {"dataset_id": "dashmint-synthetic-master", "schema_version": "0.1", "generator_version": "0.1.0", "global_seed": config.seed, "as_of_date": str(config.as_of_date), "synthetic_only": True},
            "industry": industry, "policies": policies, "customers": customers, "parties": parties, "applications": applications, "legal_documents": legal_documents,
            "financials": financials, "transactions": transactions, "cic_reports": cic_reports, "kyc_screenings": kyc_screenings, "collateral": collateral, "relationships": relationships}


def validate_master_data(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    customers, applications = data["customers"], data["applications"]
    customer_ids, app_ids = {x["customer_id"] for x in customers}, {x["application_id"] for x in applications}
    industry_codes, party_ids = {x["industry_code"] for x in data["industry"]}, {x["party_id"] for x in data["parties"]}
    collateral_ids = {x["collateral_id"] for x in data["collateral"]}
    for key, rows, identity in [("customers", customers, "customer_id"), ("applications", applications, "application_id"), ("legal_documents", data["legal_documents"], "document_id")]:
        values = [x[identity] for x in rows]
        if len(values) != len(set(values)): errors.append(f"{key}: duplicate IDs")
    for c in customers:
        if c["industry_code"] not in industry_codes or c["representative_party_id"] not in party_ids: errors.append(f"{c['customer_id']}: broken customer reference")
        if date.fromisoformat(c["incorporation_date"]) > date.fromisoformat(c["as_of_date"]): errors.append(f"{c['customer_id']}: future incorporation")
    for app in applications:
        if app["customer_id"] not in customer_ids or app["requested_amount"] <= 0 or app["tenor_months"] <= 0: errors.append(f"{app['application_id']}: invalid application")
        if any(x not in collateral_ids for x in app["proposed_collateral_ids"]): errors.append(f"{app['application_id']}: missing collateral")
    for f in data["financials"]:
        if f["assets"] != f["liabilities"] + f["equity"]: errors.append(f"{f['financial_id']}: balance mismatch")
        if f["opening_cash"] + f["net_cash_flow"] != f["ending_cash"]: errors.append(f"{f['financial_id']}: cashflow mismatch")
    for n, c in enumerate(customers, 1):
        txs = [x for x in data["transactions"] if x["customer_id"] == c["customer_id"]]
        latest = next(x for x in data["financials"] if x["customer_id"] == c["customer_id"] and x["period"] == "2026-H1")
        if not 50 <= len(txs) <= 200 or txs[-1]["running_balance"] != latest["ending_cash"]: errors.append(f"{c['customer_id']}: transaction reconciliation")
    for col in data["collateral"]:
        if col["application_id"] not in app_ids or col["eligible_value"] != _money(col["valuation_amount"] * (1-col["haircut_rate"])): errors.append(f"{col['collateral_id']}: invalid collateral")
    cic = {x["customer_id"]: x for x in data["cic_reports"]}
    for rel in data["relationships"]:
        exp = sum(x["current_outstanding"] for x in cic[rel["customer_id"]]["facilities"])
        if exp != rel["current_exposure"]: errors.append(f"{rel['relationship_id']}: exposure mismatch")
    for s in data["kyc_screenings"]:
        if s["party_id"] not in party_ids or not 0 <= s["match_score"] <= 1 or (s["match_status"] == "NO_MATCH" and s["matched_mock_entity_id"]): errors.append(f"{s['screening_id']}: invalid screening")
    return errors
