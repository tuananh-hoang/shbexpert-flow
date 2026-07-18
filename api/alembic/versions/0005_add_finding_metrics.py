"""add metrics column to findings

Revision ID: 0005_add_finding_metrics
Revises: 0004_scope_finding_key_by_case
Create Date: 2026-07-18

Structured numeric metrics a deterministic tool already computed (e.g.
coverage_ratio, dscr) — previously only folded into the LLM-phrased claim
text, unrecoverable without regex-parsing free-form prose. Same rationale
as migration 0003's `citations` column: persist what an agent actually
computed, not just what it said about it. Needed so the dashboard can
render a real gauge (Collateral Coverage) instead of a placeholder.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_add_finding_metrics"
down_revision = "0004_scope_finding_key_by_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("findings", "metrics")
