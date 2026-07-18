#!/usr/bin/env bash
set -euo pipefail
#
# Bootstraps a fresh SHBExpert Flow deploy: migrate schema, seed RAG
# knowledge base, seed demo cases — the exact sequence of commands used
# by hand throughout development, consolidated into one idempotent
# script. Safe to re-run: Alembic migrations are versioned, and every
# seed script checks for existing rows before writing (each prints
# "already exists — skipping" instead of duplicating).
#
# Prereqs on the target machine before running this:
#   1. `git clone` this repo.
#   2. `cp .env.example .env` and fill in real values (DB passwords,
#      MinIO keys, LLM API key or LLM_MOCK=true — see .env.example).
#      .env is gitignored on purpose; it never travels via git or via
#      a Docker volume, only by hand or a secrets manager.
#   3. `docker compose up -d` and wait for every service to report
#      healthy (`docker compose ps`).
#
# Then: `bash scripts/bootstrap_deploy.sh`
#
# Why no data backup/restore step exists here: almost everything this
# system currently holds (all demo cases, both RAG collections) is
# reproducible from the seed scripts this file calls — the scripts in
# git are the source of truth, not whatever happens to be sitting in
# the local Docker named volumes (pg_data/minio_data/qdrant_data).
# Deploying is: bring up empty infrastructure, then regenerate.

echo "==> Alembic migrate..."
docker compose run --rm api alembic upgrade head

echo "==> Seeding RAG knowledge base (Qdrant)..."
docker compose run --rm mcp-rag python -m scripts.seed_policies

echo "==> Seeding demo cases..."
docker compose run --rm api python -m scripts.seed_case_c06
docker compose run --rm api python -m scripts.seed_case_c07
docker compose run --rm api python -m scripts.seed_case_c08
docker compose run --rm api python -m scripts.seed_synthetic_cases

echo "==> Done. Dashboard: http://<host>:3000"
