"""revoke UPDATE/DELETE on events from the app runtime role

Revision ID: 0002_revoke_events_mutation
Revises: 92bd99c6379c
Create Date: 2026-07-17

Makes the audit log's append-only guarantee (FR-12, overview.md nguyên
tắc 6) a DB-enforced fact instead of a code convention. `shbapp` (the role
api/worker actually connect as — see postgres/init/01-init-app-role.sh)
gets SELECT/INSERT on `events` via the default-privilege grant set up at
Postgres init time, but UPDATE/DELETE are explicitly revoked here. Even a
bug in shared/state.py that tried to mutate a past event would fail at
the database, not just at code review.
"""
from __future__ import annotations

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_revoke_events_mutation"
down_revision = "92bd99c6379c"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("SHBAPP_USER", "shbapp")


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE, DELETE ON events FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT UPDATE, DELETE ON events TO {APP_ROLE}")
