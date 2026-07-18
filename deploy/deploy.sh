#!/usr/bin/env bash
# Runs ON the VM, in /opt/shbexpert. Brings the stack up, then applies DB
# migrations and seeds the demo data. Safe to re-run (compose is
# idempotent; migrations are versioned).
#
# `.env` is NOT shipped in the deploy artifact — it lives only on the VM
# and holds the real secrets (DB passwords, FPT_API_KEY, APP_DOMAIN).
# Shipping it would overwrite hand-edited secrets on every redeploy, so
# the tarball deliberately excludes it. Seed a new machine by copying
# .env.example to .env and filling it in before running this script.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "ERROR: .env missing on this machine. Copy .env.example to .env and" >&2
  echo "fill in real values (see the note above) before deploying." >&2
  exit 1
fi

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo ">> Building & starting stack..."
$COMPOSE up -d --build

echo ">> Waiting for api to become healthy..."
for _ in $(seq 1 60); do
  if $COMPOSE ps api | grep -q "healthy"; then echo "api healthy"; break; fi
  sleep 5
done

echo ">> DB migrations (alembic)..."
$COMPOSE run --rm api alembic upgrade head

# seed_policies must run in mcp-rag (it has fastembed + the pre-warmed
# embedding model cache); the golden cases run in api (they write directly
# to Postgres/MinIO via shared/). There is no combined seed_cases module —
# the cases are individual scripts/seed_case_c0*.py files.
echo ">> Seeding policy pack into qdrant (mcp-rag)..."
$COMPOSE run --rm mcp-rag python -m scripts.seed_policies

# Reference data MUST be seeded before the cases. The golden-case seeds
# insert rows into checklist_completion / customer-360 tables that carry
# foreign keys into these reference tables — running the cases first fails
# with ForeignKeyViolation (e.g. checklist_id=LC-VALUATION-EXPIRY-60D not
# present in legal_checklist_template). These two scripts arrived with the
# Collateral/Legal and Customer360 agents and are easy to miss.
echo ">> Seeding reference data: collateral + legal checklist templates (api)..."
$COMPOSE run --rm api python -m scripts.seed_collateral_reference

echo ">> Seeding reference data: customer 360 (api)..."
$COMPOSE run --rm api python -m scripts.seed_customer360_reference

echo ">> Seeding golden cases (api)..."
for c in c06 c07 c08; do
  $COMPOSE run --rm api python -m scripts.seed_case_"$c"
done

echo ">> Seeding synthetic cases (api)..."
$COMPOSE run --rm api python -m scripts.seed_synthetic_cases

echo ">> Done. Current state:"
$COMPOSE ps
