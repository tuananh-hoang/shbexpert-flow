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
    BigInteger,
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
    # Real deterministic-tool numbers (e.g. coverage_ratio, dscr) kept
    # structured for dashboard gauges/numbers — see Citation's sibling
    # comment in shared/schemas.py::FindingIn for why this exists.
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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


# ---------------------------------------------------------------------------
# Collateral & Legal domain — worker/app/agents/collateral.py's 4 tools
# (validate_ownership / get_valuation / calculate_coverage /
# search_legal_checklist). `collateral_id` reuses the existing convention
# (== case_id — see tools-mock's _VALUATIONS keyed by case_id) rather than
# introducing a separate bank-wide collateral master key, since this system
# is currently 1 case = 1 customer = 1 collateral item (C06/C07/C08).
#
# These are read DIRECTLY via shared.db by worker (like extracted_fields/
# requested_facility already are — see common.py's long comment on why
# reads bypass MCP entirely), NOT exposed as a new MCP tool server: they are
# plain relational facts/reference data, not pure computation (mcp-
# deterministic) or an external/semantic boundary (mcp-external/mcp-rag).
# ---------------------------------------------------------------------------
class CollateralRegistry(Base):
    """One row per collateral item — registered owner + registration
    instrument. validate_ownership's primary source."""

    __tablename__ = "collateral_registry"

    collateral_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), primary_key=True)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)  # CIF/CMND/MST
    registration_number: Mapped[str] = mapped_column(String, nullable=True)
    registration_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_authority: Mapped[str] = mapped_column(String, nullable=True)
    collateral_type: Mapped[str] = mapped_column(String, nullable=False)  # real_estate|vehicle|machinery|other
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OwnershipEncumbrance(Base):
    """Whether this collateral is already pledged/disputed elsewhere —
    validate_ownership's guardrail: encumbrance_found=true at another TCTD
    must not be silently approved."""

    __tablename__ = "ownership_encumbrance"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    encumbrance_type: Mapped[str] = mapped_column(String, nullable=False)  # the_chap|cam_co|tranh_chap
    encumbrance_holder: Mapped[str] = mapped_column(String, nullable=True)
    start_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")


class LegalDocumentStore(Base):
    """Registry-level record of the legal instrument itself (Sổ đỏ/GCN
    xe/...) — distinct from `documents` (the uploaded PDF/MinIO pointer):
    this tracks whether the ORIGINAL instrument's registry status checks
    out, not whether a scanned copy was uploaded."""

    __tablename__ = "legal_document_store"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    issue_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_original: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")


class CoOwnerRegistry(Base):
    """Co-owners (vợ/chồng, đồng thừa kế…) whose consent is required
    before the collateral can be pledged."""

    __tablename__ = "co_owner_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    co_owner_id: Mapped[str] = mapped_column(String, nullable=False)
    consent_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")  # CONFIRMED|PENDING|REFUSED


class HaircutMatrix(Base):
    """Reference table, seeded once, shared across every case (scripts/
    seed_collateral_reference.py) — NOT case-scoped. Read directly by
    collateral.py before calling calculate_collateral_coverage; the tool
    itself stays a pure function and never touches Postgres."""

    __tablename__ = "haircut_matrix"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    region: Mapped[str] = mapped_column(String, nullable=True)  # NULL = applies to all regions
    liquidity_tier: Mapped[str] = mapped_column(String, nullable=True)
    haircut_rate: Mapped[float] = mapped_column(Float, nullable=False)


class MarketPriceIndex(Base):
    """Reference time series, seeded once — used only if a valuation
    report's own value needs adjusting for a stale valuation_date. Not
    consumed yet in this pass (see plan's Rủi ro note); table exists so a
    later pass can add the adjustment without a new migration."""

    __tablename__ = "market_price_index"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    region: Mapped[str] = mapped_column(String, nullable=True)
    price_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    index_value: Mapped[float] = mapped_column(Float, nullable=False)


class RegulatoryReference(Base):
    """Reference table — the actual law/article a checklist item cites
    (mirrors Phụ lục 01/02 in the source cẩm nang). `reference_id` is a
    meaningful string key (e.g. "LUAT-DAT-DAI-2024-D188"), not a random
    uuid, so seed data and citations stay human-readable."""

    __tablename__ = "regulatory_reference"

    reference_id: Mapped[str] = mapped_column(String, primary_key=True)
    law_name: Mapped[str] = mapped_column(String, nullable=False)
    article: Mapped[str] = mapped_column(String, nullable=True)
    effective_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class LegalChecklistTemplate(Base):
    """Reference table — the authoritative structured checklist per
    collateral_type/transaction_type. `checklist_id` is a meaningful string
    key that ALSO appears in the Qdrant `legal_checklist` collection's
    payload (scripts/seed_policies.py), linking the semantic-search hit
    (citation text) back to this row's structured is_mandatory/
    legal_reference — search_legal_checklist joins the two in
    collateral.py, not inside mcp-rag itself."""

    __tablename__ = "legal_checklist_template"

    checklist_id: Mapped[str] = mapped_column(String, primary_key=True)
    collateral_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String, nullable=True)
    required_document: Mapped[str] = mapped_column(String, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legal_reference: Mapped[str] = mapped_column(ForeignKey("regulatory_reference.reference_id"), nullable=True)


class ChecklistCompletion(Base):
    """Per-case, MUTABLE workflow state — which checklist items are done
    for THIS collateral. Distinct from `extracted_fields` (append-only
    facts extracted from a document): this is tracked/updated as the RM
    completes items, so it gets its own table rather than being force-fit
    into the extraction model."""

    __tablename__ = "checklist_completion"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collateral_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, index=True)
    checklist_id: Mapped[str] = mapped_column(ForeignKey("legal_checklist_template.checklist_id"), nullable=False)
    completion_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # completed|pending|missing
    completed_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    responsible_party: Mapped[str] = mapped_column(String, nullable=True)


# ---------------------------------------------------------------------------
# Customer 360 & Credit History domain — worker/app/agents/customer360.py's
# 4 tools (get_customer_360 / query_cic_mock / analyze_cashflow /
# map_related_parties). Logical role matches ai-architecture_v2.md §7.3's
# "Credit Conduct / Customer 360" workcell.
#
# Keyed by `customer_id`, NOT `case_id` — a customer can have multiple cases
# over time, unlike collateral (1 case = 1 collateral in this system).
# `customer_id` is a plain String column with no FK, matching Case.customer_id
# itself (there is no `customers` master table for it to reference — a
# pre-existing gap, not introduced here, see plan's Rủi ro note). Read
# directly via shared.db by worker (common.py), not exposed as an MCP tool —
# same rationale as the Collateral & Legal domain section above.
# ---------------------------------------------------------------------------
class CustomerMaster(Base):
    __tablename__ = "customer_master"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    tax_code: Mapped[str] = mapped_column(String, nullable=True)
    establish_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    industry_code: Mapped[str] = mapped_column(String, nullable=True)
    legal_rep_id: Mapped[str] = mapped_column(String, nullable=True)


class CreditLimit(Base):
    """Hạn mức đã cấp theo loại (vay ngắn/trung/dài hạn, bảo lãnh, LC) —
    KHÁC với credit_obligation (dư nợ hiện tại, tools-mock
    /credit-obligations — task Collateral): limit là mức TRẦN được duyệt,
    obligation là số ĐANG dùng. limit_utilization_ratio = obligation/limit."""

    __tablename__ = "credit_limit"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    limit_type: Mapped[str] = mapped_column(String, nullable=False)
    approved_amount: Mapped[float] = mapped_column(Float, nullable=False)
    approval_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    approving_authority: Mapped[str] = mapped_column(String, nullable=True)


class RelationshipHistory(Base):
    __tablename__ = "relationship_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    relationship_start_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    product_used: Mapped[str] = mapped_column(String, nullable=True)
    branch_id: Mapped[str] = mapped_column(String, nullable=True)


class TransactionAccount(Base):
    __tablename__ = "transaction_account"

    account_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String, nullable=True)
    avg_balance: Mapped[float] = mapped_column(Float, nullable=True)
    open_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class CashflowStatementSummary(Base):
    """Dòng tiền qua tài khoản THẬT tại SHB — nguồn ĐỘC LẬP với
    cf_operating/cf_investing/cf_financing mà Financial Agent đọc từ BCTC
    khách tự nộp (worker/app/agents/financial.py). Cả hai cùng ghi finding
    issue_key=CASHFLOW_QUALITY để tạo đối chiếu chéo thật (worker/app/
    agents/customer360.py::run_cashflow_check)."""

    __tablename__ = "cashflow_statement_summary"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String, nullable=False)
    cf_operating: Mapped[float] = mapped_column(Float, nullable=True)
    cf_investing: Mapped[float] = mapped_column(Float, nullable=True)
    cf_financing: Mapped[float] = mapped_column(Float, nullable=True)
    net_cashflow: Mapped[float] = mapped_column(Float, nullable=True)


class ShareholderRegistry(Base):
    __tablename__ = "shareholder_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    shareholder_id: Mapped[str] = mapped_column(String, nullable=True)
    shareholder_name: Mapped[str] = mapped_column(String, nullable=False)
    ownership_pct: Mapped[float] = mapped_column(Float, nullable=True)


class LegalRepresentative(Base):
    __tablename__ = "legal_representative"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rep_id: Mapped[str] = mapped_column(String, nullable=True)
    rep_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=True)
    authorization_scope: Mapped[str] = mapped_column(String, nullable=True)


class GroupRelationship(Base):
    """Nhóm khách hàng liên quan theo quy định NHNN (công ty con/mẹ, cùng
    người đại diện, cùng cổ đông >20%...) — dùng cho map_related_parties."""

    __tablename__ = "group_relationship"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    related_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String, nullable=False)


class CrossGuarantee(Base):
    __tablename__ = "cross_guarantee"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    related_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    guarantee_amount: Mapped[float] = mapped_column(Float, nullable=False)


# ---------------------------------------------------------------------------
# Chat — ai-architecture_v2.md §11.8 "MVP Chat". A free-form chat UI
# (form), but every answer stays grounded in ONE case's CaseState (content)
# — see that section for the full Chat Orchestrator design (routing ->
# domain responders -> synthesis, all in `worker`, no Redis/job queue: a
# chat turn is a single synchronous HTTP request/response, streamed).
#
# 1 case = 1 thread (§11.8's deliberate simplification vs the full
# Follow-up Router's multi-thread `thread_id` concept in §5.1) — so
# ChatThread has a unique case_id, not a list of threads per case.
# ---------------------------------------------------------------------------
class ChatThread(Base):
    __tablename__ = "chat_threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatMessage(Base):
    """APPEND-ONLY, same discipline as `events` (shared/state.py::emit_event
    assigns `seq` under a per-thread advisory lock — see
    write_chat_message). `citations` is a best-effort array the Chat
    Orchestrator parses out of the model's own answer text (e.g.
    `[F-FIN-002-v1]` references) — nullable, never a gate on whether the
    message is shown (§11.8: citations are natural/optional, not an
    output-validator that downgrades the answer when absent)."""

    __tablename__ = "chat_messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.thread_id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # monotonic per thread
    role: Mapped[str] = mapped_column(String, nullable=False)  # USER | ASSISTANT | SYSTEM
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("thread_id", "seq", name="uq_chat_message_thread_seq"),)


# ---------------------------------------------------------------------------
# routing_decisions — ngã ba xanh/đỏ khi tiếp nhận hồ sơ
# ---------------------------------------------------------------------------
class RoutingDecision(Base):
    """Quyết định phân luồng của một hồ sơ vừa tiếp nhận.

    Bảng này nằm PHÍA TRÊN cả `cases` lẫn domain SLINK, không thuộc bên nào
    (spec 2026-07-19-intake-routing-design.md §2). Luồng đỏ tạo một `Case`
    và trỏ `case_id` vào đó; luồng xanh KHÔNG tạo case nào — `case_id` là
    NULL, và đó là điểm cốt lõi chứ không phải thiếu sót: luồng xanh không
    có hình dạng của một đơn vay.

    `lane`/`channel`/`segment` giữ là String chứ không phải Postgres ENUM,
    cùng lý do `Case.state` đã chọn: thêm giá trị sau là sửa code, không
    phải migration.
    """

    __tablename__ = "routing_decisions"

    routing_decision_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(String, nullable=False)  # RM_LMS | MOBILE_KHDN
    lane: Mapped[str] = mapped_column(String, nullable=False)  # GREEN | RED
    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    segment: Mapped[str] = mapped_column(String, nullable=False)  # SME | MICROSME
    product: Mapped[str] = mapped_column(String, nullable=False)
    # BigInteger, không Integer: 8 tỷ VND vượt trần Integer 32-bit (2,1 tỷ).
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    # Hai cột dưới loại trừ nhau: luồng đỏ set case_id, luồng xanh set
    # slink_application_id. Đúng một cái khác NULL.
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.case_id"), nullable=True)
    slink_application_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# SLINK — luồng xanh (ACAS-SLINK, tự động 100%, không qua Credit Officer)
#
# Cây bảng RIÊNG, không dùng chung `cases`: luồng xanh không có hình dạng
# của một đơn vay — không tài liệu, không finding, không thẩm định. Thực
# thể của nó là merchant + hạn mức thấu chi + chuỗi dòng tiền.
# Spec: docs/superpowers/specs/2026-07-19-slink-scoring-design.md §4.
# ---------------------------------------------------------------------------
class SlinkApplication(Base):
    """Một đề nghị thấu chi đi theo luồng xanh.

    Sinh ra từ một RoutingDecision có lane=GREEN. Đối xứng với `Case` của
    luồng đỏ, nhưng KHÔNG chia sẻ state machine: `status` ở đây là tiến
    trình chấm điểm tự động, không phải ALLOWED_TRANSITIONS.
    """

    __tablename__ = "slink_applications"

    slink_application_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    routing_decision_id: Mapped[str] = mapped_column(
        ForeignKey("routing_decisions.routing_decision_id"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    amount_requested_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    # QUEUED | SCORING | APPROVED | REJECTED | FAILED
    status: Mapped[str] = mapped_column(String, nullable=False, default="QUEUED")
    recommended_limit_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interest_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SlinkAgentDecision(Base):
    """Vết chạy của một agent trong engine SLINK.

    Tương đương `findings` của luồng đỏ nhưng PHẲNG hơn: không version,
    không phản biện, không conflict — engine tất định chạy một lượt, mỗi
    agent ghi đúng một dòng.
    """

    __tablename__ = "slink_agent_decisions"
    __table_args__ = (
        UniqueConstraint("slink_application_id", "agent_id", name="uq_slink_decision_app_agent"),
    )

    decision_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    slink_application_id: Mapped[str] = mapped_column(
        ForeignKey("slink_applications.slink_application_id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SlinkOverdraftEvent(Base):
    """Mọi lần chạm vào hạn mức thấu chi — APPEND-ONLY.

    Không sửa dòng cũ, cùng nguyên tắc bảng `events` của luồng đỏ (FR-12).

    `core_banking_response` lưu NGUYÊN VĂN phản hồi: core-banking là nguồn
    sự thật của hạn mức (spec lát c §2), nên khi DB ta và nó lệch nhau, cần
    biết nó đã trả về đúng cái gì chứ không chỉ biết ta diễn giải ra sao.

    `slink_application_id` nullable: sự kiện sốc dòng tiền điều chỉnh hạn
    mức đang có, không sinh từ một đề nghị nào.
    """

    __tablename__ = "slink_overdraft_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    slink_application_id: Mapped[str | None] = mapped_column(
        ForeignKey("slink_applications.slink_application_id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)  # ISSUE | ADJUST | SUSPEND
    limit_before_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    limit_after_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interest_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    core_banking_response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
