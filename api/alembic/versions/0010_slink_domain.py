"""add SLINK domain (luồng xanh) + liên kết từ routing_decisions

Revision ID: 0010_slink_domain
Revises: 0009_intake_routing
Create Date: 2026-07-19

Cây bảng RIÊNG cho luồng xanh — không đụng `cases`, không đụng
ALLOWED_TRANSITIONS. Spec: docs/superpowers/specs/2026-07-19-slink-scoring-design.md §4.

routing_decisions.slink_application_id đối xứng với case_id đã có: luồng đỏ
set case_id, luồng xanh set slink_application_id. Không đặt ForeignKey hai
chiều vì slink_applications lại trỏ ngược về routing_decisions — vòng FK sẽ
làm cả hai bảng không insert được nếu không hoãn ràng buộc.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_slink_domain"
down_revision = "0009_intake_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slink_applications",
        sa.Column("slink_application_id", sa.String(), primary_key=True),
        sa.Column(
            "routing_decision_id",
            sa.String(),
            sa.ForeignKey("routing_decisions.routing_decision_id"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("amount_requested_vnd", sa.BigInteger(), nullable=False),
        sa.Column("tenor_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="QUEUED"),
        sa.Column("recommended_limit_vnd", sa.BigInteger(), nullable=True),
        sa.Column("interest_rate_pct", sa.Float(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_slink_applications_status", "slink_applications", ["status"])

    op.create_table(
        "slink_agent_decisions",
        sa.Column("decision_id", sa.String(), primary_key=True),
        sa.Column(
            "slink_application_id",
            sa.String(),
            sa.ForeignKey("slink_applications.slink_application_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("metrics", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slink_application_id", "agent_id", name="uq_slink_decision_app_agent"),
    )
    op.create_index(
        "ix_slink_agent_decisions_application",
        "slink_agent_decisions",
        ["slink_application_id"],
    )

    op.add_column("routing_decisions", sa.Column("slink_application_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("routing_decisions", "slink_application_id")
    op.drop_index("ix_slink_agent_decisions_application", table_name="slink_agent_decisions")
    op.drop_table("slink_agent_decisions")
    op.drop_index("ix_slink_applications_status", table_name="slink_applications")
    op.drop_table("slink_applications")
