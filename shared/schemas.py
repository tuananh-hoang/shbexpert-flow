"""Pydantic schemas mirroring ai-architecture.md §9 / Phụ lục A exactly.

These are the wire/validation shapes used at boundaries (API request/response
bodies, MCP tool inputs/outputs, LangGraph node outputs) — the ORM models in
shared/models.py are the storage shape. Keeping them separate means a
storage-layer refactor (e.g. splitting a JSONB column) doesn't silently
change what an agent is allowed to send.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal["FACT", "INFERENCE"]
Stance = Literal["SUPPORT", "CAUTION", "OPPOSE", "NEED_DATA"]
Severity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
ConflictStatus = Literal["OPEN", "RESOLVED", "UNRESOLVED"]
Recommendation = Literal["APPROVE", "APPROVE_WITH_CONDITIONS", "REFER", "REJECT", "NEED_INFO"]


class Citation(BaseModel):
    """A structured pointer into RAG-retrieved knowledge (policy clause or
    legal checklist item) that grounded a finding's claim — distinct from
    `evidence_ids` (which point at ExtractedField/document evidence).
    Mirrors what mcp-rag's search_policy/search_legal_checklist already
    return (mcp-rag/app/server.py), just persisted instead of only being
    folded into the LLM prompt string and discarded afterward."""

    source_type: Literal["POLICY", "LEGAL_CHECKLIST"]
    source_id: str  # policy_id, or collateral_type for a checklist item
    version: str | None = None
    section: str | None = None  # POLICY only
    effective_date: str | None = None  # POLICY only
    text: str  # the actual clause/checklist text cited
    score: float  # Qdrant similarity score — surfaces match confidence, not just a bare quote


class FindingIn(BaseModel):
    """What an expert agent hands to the state layer. `version` and
    `change_reason` are NOT set by the agent — write_finding() computes
    version server-side (Phase 1 shared/state.py) so an agent can never
    forge its own version history."""

    case_id: str
    agent_id: str
    issue_key: str
    claim_type: ClaimType
    claim: str
    stance: Stance
    severity: Severity
    evidence_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    # Real numbers a deterministic tool (mcp-deterministic) already
    # computed — e.g. {"coverage_ratio": 1.267}, {"dscr": 1.72} — kept
    # structured so the dashboard can render a gauge/number directly
    # instead of regex-parsing the LLM-phrased claim text (fragile,
    # especially with a real LLM varying its wording run to run).
    metrics: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str | None = None
    change_reason: str | None = None  # required when this supersedes a prior finding_key


class FindingOut(FindingIn):
    finding_key: str
    version: int
    created_at: dt.datetime

    @property
    def display_id(self) -> str:
        return f"{self.finding_key}-v{self.version}"


class TargetedQuestion(BaseModel):
    to_agent: str
    question: str
    required_evidence: list[str] = Field(default_factory=list)


class ConflictRecordOut(BaseModel):
    conflict_id: str
    case_id: str
    issue_key: str
    source_findings: list[str]  # ["F-FIN-008-v1", "F-COL-004-v1"]
    targeted_questions: list[TargetedQuestion] = Field(default_factory=list)
    round: int
    status: ConflictStatus
    created_at: dt.datetime
    updated_at: dt.datetime


class HardGateResult(BaseModel):
    gate_id: str
    status: Literal["PASS", "FAIL", "REVIEW"]
    reason: str | None = None


class ScoreEntry(BaseModel):
    dimension: str
    score: float
    max: float


class DecisionPackageIn(BaseModel):
    """What Decision Synthesis hands to the state layer — `decision_id`
    and `created_at` are server-assigned, matching the Finding split."""

    case_id: str
    recommendation: Recommendation
    requested_amount_vnd: float | None = None
    recommended_amount_vnd: float | None = None
    recommended_tenor_months: int | None = None
    hard_gates: list[HardGateResult] = Field(default_factory=list)
    scores: list[ScoreEntry] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    conditions_precedent: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    decision_matrix_version: str | None = None


class DecisionPackageOut(BaseModel):
    decision_id: str
    case_id: str
    recommendation: Recommendation
    requested_amount_vnd: float | None = None
    recommended_amount_vnd: float | None = None
    recommended_tenor_months: int | None = None
    hard_gates: list[HardGateResult] = Field(default_factory=list)
    scores: list[ScoreEntry] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)  # finding display_ids
    risks: list[str] = Field(default_factory=list)
    conditions_precedent: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    decision_matrix_version: str | None = None
    version: int
    created_at: dt.datetime


class Actor(BaseModel):
    type: Literal["AGENT", "USER", "SYSTEM"]
    id: str


class EventOut(BaseModel):
    event_id: str
    case_id: str
    seq: int
    event_type: str
    actor: Actor
    timestamp: dt.datetime
    payload: dict = Field(default_factory=dict)
    versions: dict = Field(default_factory=dict)
