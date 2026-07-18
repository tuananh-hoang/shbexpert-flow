"""add routing_decisions (phân luồng xanh/đỏ khi tiếp nhận)

Revision ID: 0009_intake_routing
Revises: 0008_chat_domain
Create Date: 2026-07-19

Bảng nằm PHÍA TRÊN cả `cases` lẫn domain SLINK, không thuộc bên nào — spec
docs/superpowers/specs/2026-07-19-intake-routing-design.md §2. Luồng đỏ tạo
Case và trỏ case_id vào đó; luồng xanh không tạo case nào nên case_id NULL.

Không đụng tới `cases` hay ALLOWED_TRANSITIONS.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_intake_routing"
down_revision = "0008_chat_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routing_decisions",
        sa.Column("routing_decision_id", sa.String(), primary_key=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("lane", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("segment", sa.String(), nullable=False),
        sa.Column("product", sa.String(), nullable=False),
        # BigInteger: 8 tỷ VND vượt trần Integer 32-bit (2,1 tỷ).
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("tenor_months", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.case_id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_routing_decisions_lane", "routing_decisions", ["lane"])
    op.create_index("ix_routing_decisions_case_id", "routing_decisions", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_routing_decisions_case_id", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_lane", table_name="routing_decisions")
    op.drop_table("routing_decisions")
