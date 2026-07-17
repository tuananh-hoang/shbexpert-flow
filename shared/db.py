"""SQLAlchemy engine/session factory shared by api and worker.

DATABASE_URL is read from the environment (see .env.example). Both
processes connect to the same Postgres instance; api owns migrations
(Alembic lives under api/alembic) but the engine/session helpers are
shared so worker can use the exact same ORM models without duplicating
connection logic.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://shbuser:shbpass@localhost:5432/shbexpert",
)

# pool_pre_ping avoids "server closed the connection unexpectedly" after
# idle periods (common with containerized Postgres restarts during dev).
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context-managed session — commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """Used by /health endpoints — raises if Postgres is unreachable."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
