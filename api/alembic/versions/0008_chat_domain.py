"""add chat_threads/chat_messages (ai-architecture_v2.md §11.8 MVP Chat)

Revision ID: 0008_chat_domain
Revises: 0007_customer360
Create Date: 2026-07-19

1 case = 1 thread — `chat_threads.case_id` is UNIQUE, not a list of
threads per case (§11.8's deliberate simplification). `chat_messages` is
append-only with a per-thread monotonic `seq`, same discipline as the
`events` table (see shared/state.py::write_chat_message /
emit_event for the identical advisory-lock pattern).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_chat_domain"
down_revision = "0007_customer360"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("thread_id"),
        sa.UniqueConstraint("case_id", name="uq_chat_thread_case_id"),
    )

    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.thread_id"]),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint("thread_id", "seq", name="uq_chat_message_thread_seq"),
    )
    op.create_index(op.f("ix_chat_messages_thread_id"), "chat_messages", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_messages_thread_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
