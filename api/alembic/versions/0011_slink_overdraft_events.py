"""add slink_overdraft_events (Operations — cấp/điều chỉnh/treo hạn mức)

Revision ID: 0011_slink_overdraft_events
Revises: 0010_slink_domain
Create Date: 2026-07-19

Append-only, cùng nguyên tắc bảng `events` của luồng đỏ (FR-12).
Spec: docs/superpowers/specs/2026-07-19-slink-operations-design.md §5

Không thêm ràng buộc CHECK trên slink_applications.status: trạng thái vốn
là String tự do (cùng lý do Case.state đã chọn), thêm ISSUING/ISSUED/
ISSUE_FAILED chỉ là thay đổi code.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_slink_overdraft_events"
down_revision = "0010_slink_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slink_overdraft_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column(
            "slink_application_id",
            sa.String(),
            sa.ForeignKey("slink_applications.slink_application_id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("limit_before_vnd", sa.BigInteger(), nullable=True),
        sa.Column("limit_after_vnd", sa.BigInteger(), nullable=True),
        sa.Column("interest_rate_pct", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("core_banking_response", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_slink_overdraft_events_customer", "slink_overdraft_events", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_slink_overdraft_events_customer", table_name="slink_overdraft_events")
    op.drop_table("slink_overdraft_events")
