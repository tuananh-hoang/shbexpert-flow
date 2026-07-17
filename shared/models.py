"""SQLAlchemy ORM models for the 7 CaseState table groups + audit event log.

Matches data-flow.md §1 exactly:
    identity | documents | tasks | findings | conflicts | decision | audit

Design notes that matter (don't "simplify" these away without re-reading
the architecture docs first):

- `findings` is APPEND-ONLY per logical finding. `finding_key` is the
  stable issue-scoped id (e.g. "F-FIN-008"); each edit inserts a NEW row
  with `version` incremented — never UPDATE an existing finding row. The
  human-readable compound id from the docs ("F-FIN-008-v1") is
  `f"{finding_key}-v{version}"`, not a stored column.
- `events` is APPEND-ONLY (FR-12). The migration that creates this table
  additionally revokes UPDATE/DELETE from the app DB role — see Phase 1
  migration 0002.
- Every JSON-ish field (dependency, evidence_ids, payload, ...) is stored
  as JSONB, not a serialized string, so Postgres can index/query into it
  later without a migration.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------
class Case(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    product: Mapped[str] = mapped_column(String, nullable=False)
    requested_facility: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    # State machine states — data-flow.md §2. Kept as plain String (not a
    # Postgres ENUM) so adding a state later is a code change, not a
    # migration; validity is enforced in shared/state.py, not the DB type.
    state: Mapped[str] = mapped_column(String, nullable=False, default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------
class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    minio_key: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    review_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExtractedField(Base):
    """Stand-in for what OCR/extraction would normally produce — per the
    user's constraint, this table is seeded directly (scripts/seed_case_c06)
    instead of being populated by a Document Processing Pipeline."""

    __tablename__ = "extracted_fields"

    field_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), nullable=False)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"type": ..., "raw": ...}
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    page: Mapped[int] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict] = mapped_column(JSONB, nullable=True)  # {"x0","y0","x1","y1"}


# ---------------------------------------------------------------------------
# tasks (Orchestrator TaskPlan)
# ---------------------------------------------------------------------------
class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    dependency: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    allowed_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# findings — blackboard (ai-architecture.md §9.1). APPEND-ONLY per finding_key.
# ---------------------------------------------------------------------------
class Finding(Base):
    __tablename__ = "findings"
    # Scoped by case_id, not just (finding_key, version) — finding_key
    # numbering (F-FIN-001, ...) is minted per-case (_next_finding_key in
    # shared/state.py), so two different cases' first Financial finding
    # both legitimately mint "F-FIN-001" v1. A single-case-only constraint
    # here caused a real UniqueViolation the moment a second case existed
    # (surfaced when Application Queue support added case C07/C08).
    __table_args__ = (UniqueConstraint("case_id", "finding_key", "version", name="uq_case_finding_key_version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    finding_key: Mapped[str] = mapped_column(String, nullable=False, index=True)  # e.g. "F-FIN-008"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    issue_key: Mapped[str] = mapped_column(String, nullable=False, index=True)  # conflict-detection key
    claim_type: Mapped[str] = mapped_column(String, nullable=False)  # FACT | INFERENCE
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    stance: Mapped[str] = mapped_column(String, nullable=False)  # SUPPORT|CAUTION|OPPOSE|NEED_DATA
    severity: Mapped[str] = mapped_column(String, nullable=False)  # INFO..CRITICAL
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # RAG-retrieved policy/legal citations (Citation schema) — distinct from
    # evidence_ids (ExtractedField/document evidence). Added Phase 8.
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    change_reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def display_id(self) -> str:
        """e.g. "F-FIN-008-v2" — the compound id used in docs/UI, never stored."""
        return f"{self.finding_key}-v{self.version}"


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------
class ConflictRecord(Base):
    __tablename__ = "conflicts"

    conflict_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    issue_key: Mapped[str] = mapped_column(String, nullable=False)
    source_findings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["F-FIN-008-v1", ...]
    targeted_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")  # OPEN|RESOLVED|UNRESOLVED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------
class DecisionPackage(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String, nullable=False)
    requested_amount_vnd: Mapped[float] = mapped_column(Float, nullable=True)
    recommended_amount_vnd: Mapped[float] = mapped_column(Float, nullable=True)
    recommended_tenor_months: Mapped[int] = mapped_column(Integer, nullable=True)
    hard_gates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scores: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # finding_ids
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # finding_ids
    conditions_precedent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    dissent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # finding_ids
    unresolved_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String, nullable=True)
    decision_matrix_version: Mapped[str] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# audit — APPEND-ONLY (FR-12). UPDATE/DELETE revoked from the app role in
# migration 0002_revoke_events_mutation.py, not just "by convention" here.
# ---------------------------------------------------------------------------
class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # monotonic per case_id
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"type": "AGENT"|"USER"|"SYSTEM", "id": ...}
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # policy/formula/model/tool versions

    __table_args__ = (UniqueConstraint("case_id", "seq", name="uq_event_case_seq"),)
