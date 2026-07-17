"""scope findings unique constraint by case_id

Revision ID: 0004_scope_finding_key_by_case
Revises: 0003_add_finding_citations
Create Date: 2026-07-18

The original `uq_finding_key_version` constraint was `(finding_key,
version)` only — fine while exactly one case (C06) existed, but a real
bug once a second case exists: finding_key numbering (F-FIN-001, ...) is
minted PER-CASE (shared/state.py::_next_finding_key), so two different
cases' first Financial finding both legitimately mint "F-FIN-001" v1,
and the old constraint rejected the second case's insert outright
(UniqueViolation). Widening the constraint to (case_id, finding_key,
version) is the correct fix — the old one only appeared safe because
nothing had exercised the multi-case path yet.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_scope_finding_key_by_case"
down_revision = "0003_add_finding_citations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_finding_key_version", "findings", type_="unique")
    op.create_unique_constraint(
        "uq_case_finding_key_version", "findings", ["case_id", "finding_key", "version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_case_finding_key_version", "findings", type_="unique")
    op.create_unique_constraint("uq_finding_key_version", "findings", ["finding_key", "version"])
