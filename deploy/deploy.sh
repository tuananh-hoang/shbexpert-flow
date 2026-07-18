#!/usr/bin/env bash
# Runs ON the VM, in /opt/shbexpert. Brings the stack up, then applies DB
# migrations and seeds the demo data. Safe to re-run (compose is
# idempotent; migrations are versioned).
set -euo pipefail
cd "$(dirname "$0")/.."

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

echo ">> Seeding golden cases (api)..."
for c in c06 c07 c08; do
  $COMPOSE run --rm api python -m scripts.seed_case_"$c"
done

echo ">> Done. Current state:"
$COMPOSE ps
