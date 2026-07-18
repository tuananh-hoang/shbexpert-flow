"""add collateral & legal domain tables

Revision ID: 0006_collateral_domain
Revises: 0005_add_finding_metrics
Create Date: 2026-07-18

Full relational schema for the 4 Collateral & Legal Agent tools
(validate_ownership / get_valuation / calculate_collateral_coverage /
search_legal_checklist) — see shared/models.py's "Collateral & Legal
domain" section for why these are read directly via shared.db (like
extracted_fields) rather than exposed as a new MCP server.

`collateral_id` reuses the existing case_id convention (1 case = 1
collateral in this system, matching tools-mock's _VALUATIONS keyed by
case_id). Reference tables (haircut_matrix, market_price_index,
legal_checklist_template, regulatory_reference) are NOT case-scoped —
seeded once via scripts/seed_collateral_reference.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_collateral_domain"
down_revision = "0005_add_finding_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collateral_registry",
        sa.Column("collateral_id", sa.String(), nullable=False),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("registration_number", sa.String(), nullable=True),
        sa.Column("registration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_authority", sa.String(), nullable=True),
        sa.Column("collateral_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collateral_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("collateral_id"),
    )

    op.create_table(
        "ownership_encumbrance",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collateral_id", sa.String(), nullable=False),
        sa.Column("encumbrance_type", sa.String(), nullable=False),
        sa.Column("encumbrance_holder", sa.String(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["collateral_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ownership_encumbrance_collateral_id"), "ownership_encumbrance", ["collateral_id"], unique=False)

    op.create_table(
        "legal_document_store",
        sa.Column("doc_id", sa.String(), nullable=False),
        sa.Column("collateral_id", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("issue_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_original", sa.Boolean(), nullable=False),
        sa.Column("verification_status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["collateral_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("doc_id"),
    )
    op.create_index(op.f("ix_legal_document_store_collateral_id"), "legal_document_store", ["collateral_id"], unique=False)

    op.create_table(
        "co_owner_registry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collateral_id", sa.String(), nullable=False),
        sa.Column("co_owner_id", sa.String(), nullable=False),
        sa.Column("consent_status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["collateral_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_co_owner_registry_collateral_id"), "co_owner_registry", ["collateral_id"], unique=False)

    op.create_table(
        "haircut_matrix",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collateral_type", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("liquidity_tier", sa.String(), nullable=True),
        sa.Column("haircut_rate", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_haircut_matrix_collateral_type"), "haircut_matrix", ["collateral_type"], unique=False)

    op.create_table(
        "market_price_index",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collateral_type", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("price_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("index_value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_price_index_collateral_type"), "market_price_index", ["collateral_type"], unique=False)

    op.create_table(
        "regulatory_reference",
        sa.Column("reference_id", sa.String(), nullable=False),
        sa.Column("law_name", sa.String(), nullable=False),
        sa.Column("article", sa.String(), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("reference_id"),
    )

    op.create_table(
        "legal_checklist_template",
        sa.Column("checklist_id", sa.String(), nullable=False),
        sa.Column("collateral_type", sa.String(), nullable=False),
        sa.Column("transaction_type", sa.String(), nullable=True),
        sa.Column("required_document", sa.String(), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("legal_reference", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["legal_reference"], ["regulatory_reference.reference_id"]),
        sa.PrimaryKeyConstraint("checklist_id"),
    )
    op.create_index(op.f("ix_legal_checklist_template_collateral_type"), "legal_checklist_template", ["collateral_type"], unique=False)

    op.create_table(
        "checklist_completion",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("collateral_id", sa.String(), nullable=False),
        sa.Column("checklist_id", sa.String(), nullable=False),
        sa.Column("completion_status", sa.String(), nullable=False),
        sa.Column("completed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsible_party", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["collateral_id"], ["cases.case_id"]),
        sa.ForeignKeyConstraint(["checklist_id"], ["legal_checklist_template.checklist_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checklist_completion_collateral_id"), "checklist_completion", ["collateral_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_checklist_completion_collateral_id"), table_name="checklist_completion")
    op.drop_table("checklist_completion")
    op.drop_index(op.f("ix_legal_checklist_template_collateral_type"), table_name="legal_checklist_template")
    op.drop_table("legal_checklist_template")
    op.drop_table("regulatory_reference")
    op.drop_index(op.f("ix_market_price_index_collateral_type"), table_name="market_price_index")
    op.drop_table("market_price_index")
    op.drop_index(op.f("ix_haircut_matrix_collateral_type"), table_name="haircut_matrix")
    op.drop_table("haircut_matrix")
    op.drop_index(op.f("ix_co_owner_registry_collateral_id"), table_name="co_owner_registry")
    op.drop_table("co_owner_registry")
    op.drop_index(op.f("ix_legal_document_store_collateral_id"), table_name="legal_document_store")
    op.drop_table("legal_document_store")
    op.drop_index(op.f("ix_ownership_encumbrance_collateral_id"), table_name="ownership_encumbrance")
    op.drop_table("ownership_encumbrance")
    op.drop_table("collateral_registry")
