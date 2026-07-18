#!/bin/bash
# Runs once, only when the Postgres data volume is first initialized
# (docker-entrypoint-initdb.d convention). Creates a LEAST-PRIVILEGE role
# for api/worker runtime traffic, separate from $POSTGRES_USER (which stays
# a superuser used only by Alembic for DDL).
#
# Why this matters: Postgres superusers bypass every GRANT/REVOKE check.
# If api/worker connected as $POSTGRES_USER, "REVOKE UPDATE, DELETE ON
# events FROM <app_user>" (migration 0002) would be a no-op — the
# append-only audit log guarantee would be enforced by nothing but
# convention. Runtime traffic MUST go through this role for the DB-level
# guarantee to be real.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE ${SHBAPP_USER} WITH LOGIN PASSWORD '${SHBAPP_PASSWORD}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${SHBAPP_USER};
    GRANT USAGE ON SCHEMA public TO ${SHBAPP_USER};

    -- Applies to tables created AFTER this point by the role running this
    -- script ($POSTGRES_USER) — which is exactly the role Alembic migrations
    -- connect as. So every table `alembic upgrade head` creates later
    -- automatically grants these to ${SHBAPP_USER}; migration 0002 then
    -- narrows `events` specifically by revoking UPDATE/DELETE on it.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${SHBAPP_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO ${SHBAPP_USER};
EOSQL
