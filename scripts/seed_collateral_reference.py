"""Seed reference/lookup tables for the Collateral & Legal Agent (NOT
case-scoped — shared across every case, unlike scripts/seed_case_c0*.py):
haircut_matrix, regulatory_reference, legal_checklist_template,
market_price_index.

`checklist_id` values here MUST match the `checklist_id` metadata seeded
into Qdrant's `legal_checklist` collection (scripts/seed_policies.py) —
collateral.py::run_legal_checklist_check joins the two by this id to
combine semantic citation text with structured is_mandatory/status.

Known scope simplification: `collateral_type` here is the DOCUMENT type
("valuation_certificate"), matching worker/app/agents/collateral.py's
existing COLLATERAL_TYPE constant — NOT the underlying physical asset type
(real_estate/vehicle/machinery). The system doesn't track a separate
physical-asset-type field yet, so haircut_matrix/legal_checklist_template
rows are keyed the same way the rest of the code already queries them.
Extra real_estate/vehicle/machinery rows are seeded anyway (reference data,
unused by current code) so a later pass can wire up real asset-type
tracking without a new migration.

Run with: `docker compose run --rm api python -m scripts.seed_collateral_reference`
Idempotent — skips any row whose primary key already exists.
"""
from __future__ import annotations

import datetime as dt

from shared.db import get_session
from shared.models import HaircutMatrix, LegalChecklistTemplate, MarketPriceIndex, RegulatoryReference

REGULATORY_REFERENCES = [
    {"reference_id": "TT-DINH-GIA-2021", "law_name": "Thông tư hướng dẫn thẩm định giá tài sản", "article": "Điều 12", "effective_date": dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)},
    {"reference_id": "LUAT-KDBDS-2023-D9", "law_name": "Luật Kinh doanh bất động sản 2023", "article": "Điều 9", "effective_date": dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc)},
]

LEGAL_CHECKLIST_TEMPLATES = [
    {
        "checklist_id": "LC-VALUATION-EXPIRY-60D",
        "collateral_type": "valuation_certificate",
        "transaction_type": "the_chap",
        "required_document": "Chứng thư định giá còn hiệu lực tối thiểu 60 ngày kể từ ngày giải ngân dự kiến",
        "is_mandatory": True,
        "legal_reference": "TT-DINH-GIA-2021",
    },
    {
        "checklist_id": "LC-VALUATION-APPRAISER-LICENSE",
        "collateral_type": "valuation_certificate",
        "transaction_type": "the_chap",
        "required_document": "Chứng thư có chữ ký thẩm định viên có chứng chỉ hành nghề hợp lệ",
        "is_mandatory": True,
        "legal_reference": "TT-DINH-GIA-2021",
    },
    {
        "checklist_id": "LC-REAL-ESTATE-TITLE",
        "collateral_type": "real_estate",
        "transaction_type": "the_chap",
        "required_document": "Giấy chứng nhận quyền sử dụng đất hợp lệ, đã đăng ký giao dịch bảo đảm",
        "is_mandatory": True,
        "legal_reference": "LUAT-KDBDS-2023-D9",
    },
]

# haircut_rate applied to forced_sale_value in calculate_collateral_coverage.
# "valuation_certificate" is the row actually queried by the current code
# (see module docstring); real_estate/vehicle/machinery are reference data
# for a future pass that tracks physical asset type separately.
HAIRCUT_MATRIX = [
    {"collateral_type": "valuation_certificate", "region": None, "liquidity_tier": None, "haircut_rate": 0.15},
    {"collateral_type": "real_estate", "region": None, "liquidity_tier": None, "haircut_rate": 0.25},
    {"collateral_type": "vehicle", "region": None, "liquidity_tier": None, "haircut_rate": 0.45},
    {"collateral_type": "machinery", "region": None, "liquidity_tier": None, "haircut_rate": 0.55},
]

# Not consumed by any tool yet (see plan's "Rủi ro" note — deferred to a
# later pass that adjusts a stale valuation against a price index). Seeded
# so the table isn't empty and the schema is exercised at least once.
MARKET_PRICE_INDEX = [
    {"collateral_type": "real_estate", "region": "HN", "price_date": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), "index_value": 108.5},
]


def main() -> None:
    with get_session() as session:
        added = {"regulatory_reference": 0, "legal_checklist_template": 0, "haircut_matrix": 0, "market_price_index": 0}

        for row in REGULATORY_REFERENCES:
            if session.get(RegulatoryReference, row["reference_id"]) is not None:
                continue
            session.add(RegulatoryReference(**row))
            added["regulatory_reference"] += 1

        session.flush()  # regulatory_reference rows must be committed before legal_checklist_template's FK insert below

        for row in LEGAL_CHECKLIST_TEMPLATES:
            if session.get(LegalChecklistTemplate, row["checklist_id"]) is not None:
                continue
            session.add(LegalChecklistTemplate(**row))
            added["legal_checklist_template"] += 1

        session.flush()

        from sqlalchemy import select

        for row in HAIRCUT_MATRIX:
            exists = session.execute(
                select(HaircutMatrix).where(HaircutMatrix.collateral_type == row["collateral_type"])
            ).scalars().first()
            if exists is not None:
                continue
            session.add(HaircutMatrix(**row))
            added["haircut_matrix"] += 1

        for row in MARKET_PRICE_INDEX:
            exists = session.execute(
                select(MarketPriceIndex).where(MarketPriceIndex.collateral_type == row["collateral_type"])
            ).scalars().first()
            if exists is not None:
                continue
            session.add(MarketPriceIndex(**row))
            added["market_price_index"] += 1

        print(f"seeded collateral reference tables: {added}")


if __name__ == "__main__":
    main()
