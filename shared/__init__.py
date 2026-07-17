"""Shared package used by both `api` and `worker` containers.

Both services are built with the repo root as Docker build context so this
package can be copied into each image (see api/Dockerfile, worker/Dockerfile).
It holds the SQLAlchemy engine/session setup and, from Phase 1 onward, the
ORM models + state-layer functions that are the single source of truth for
writing CaseState (findings/tasks/conflicts/decisions/events).
"""
