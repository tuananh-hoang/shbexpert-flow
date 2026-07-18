"""add customer 360 & credit history domain tables

Revision ID: 0007_customer360
Revises: 0006_collateral_domain
Create Date: 2026-07-18

9 tables for Customer 360 & Credit History Agent's 4 tools (get_customer_360
/ query_cic_mock / analyze_cashflow / map_related_parties) — see
shared/models.py's "Customer 360 & Credit History domain" section.

Keyed by customer_id (plain String, no FK — matches Case.customer_id's
existing lack of FK to any customers master table), NOT case_id, since a
customer can have multiple cases over time.

NOTE: revision id kept <=32 chars — alembic_version.version_num is
VARCHAR(32); migration 0006's first attempt hit
StringDataRightTruncation with a longer id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_customer360"
down_revision = "0006_collateral_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_master",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(), nullable=False),
        sa.Column("tax_code", sa.String(), nullable=True),
        sa.Column("establish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("industry_code", sa.String(), nullable=True),
        sa.Column("legal_rep_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("customer_id"),
    )

    op.create_table(
        "credit_limit",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("limit_type", sa.String(), nullable=False),
        sa.Column("approved_amount", sa.Float(), nullable=False),
        sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approving_authority", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credit_limit_customer_id"), "credit_limit", ["customer_id"], unique=False)

    op.create_table(
        "relationship_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("relationship_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_used", sa.String(), nullable=True),
        sa.Column("branch_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_relationship_history_customer_id"), "relationship_history", ["customer_id"], unique=False)

    op.create_table(
        "transaction_account",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=True),
        sa.Column("avg_balance", sa.Float(), nullable=True),
        sa.Column("open_date", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_index(op.f("ix_transaction_account_customer_id"), "transaction_account", ["customer_id"], unique=False)

    op.create_table(
        "cashflow_statement_summary",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("cf_operating", sa.Float(), nullable=True),
        sa.Column("cf_investing", sa.Float(), nullable=True),
        sa.Column("cf_financing", sa.Float(), nullable=True),
        sa.Column("net_cashflow", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cashflow_statement_summary_customer_id"), "cashflow_statement_summary", ["customer_id"], unique=False
    )

    op.create_table(
        "shareholder_registry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("shareholder_id", sa.String(), nullable=True),
        sa.Column("shareholder_name", sa.String(), nullable=False),
        sa.Column("ownership_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shareholder_registry_customer_id"), "shareholder_registry", ["customer_id"], unique=False)

    op.create_table(
        "legal_representative",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("rep_id", sa.String(), nullable=True),
        sa.Column("rep_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("authorization_scope", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_legal_representative_customer_id"), "legal_representative", ["customer_id"], unique=False)

    op.create_table(
        "group_relationship",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("related_customer_id", sa.String(), nullable=False),
        sa.Column("relationship_type", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_group_relationship_customer_id"), "group_relationship", ["customer_id"], unique=False)

    op.create_table(
        "cross_guarantee",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("related_customer_id", sa.String(), nullable=False),
        sa.Column("guarantee_amount", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cross_guarantee_customer_id"), "cross_guarantee", ["customer_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cross_guarantee_customer_id"), table_name="cross_guarantee")
    op.drop_table("cross_guarantee")
    op.drop_index(op.f("ix_group_relationship_customer_id"), table_name="group_relationship")
    op.drop_table("group_relationship")
    op.drop_index(op.f("ix_legal_representative_customer_id"), table_name="legal_representative")
    op.drop_table("legal_representative")
    op.drop_index(op.f("ix_shareholder_registry_customer_id"), table_name="shareholder_registry")
    op.drop_table("shareholder_registry")
    op.drop_index(op.f("ix_cashflow_statement_summary_customer_id"), table_name="cashflow_statement_summary")
    op.drop_table("cashflow_statement_summary")
    op.drop_index(op.f("ix_transaction_account_customer_id"), table_name="transaction_account")
    op.drop_table("transaction_account")
    op.drop_index(op.f("ix_relationship_history_customer_id"), table_name="relationship_history")
    op.drop_table("relationship_history")
    op.drop_index(op.f("ix_credit_limit_customer_id"), table_name="credit_limit")
    op.drop_table("credit_limit")
    op.drop_table("customer_master")
