"""add citations column to findings

Revision ID: 0003_add_finding_citations
Revises: 0002_revoke_events_mutation
Create Date: 2026-07-18

Structured RAG citations (policy clause / legal checklist item that
grounded a finding) — previously only folded into the claim text and the
audit event's `versions` dict (worker/app/agents/policy.py), never
persisted as a queryable, displayable field on the Finding itself.
Distinct from `evidence_ids` (ExtractedField/document evidence, unchanged).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_add_finding_citations"
down_revision = "0002_revoke_events_mutation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("findings", "citations")
