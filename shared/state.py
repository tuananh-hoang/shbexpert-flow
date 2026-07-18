"""State layer — the ONLY code path allowed to write findings/tasks/
conflicts/decisions/events. Both `api` and `worker` import this module
(rather than issuing raw SQL) so every write goes through the same
versioning + audit-event + transition-validation rules, no matter which
process makes it.

This is the concrete implementation of overview.md §6 nguyên tắc 6 ("Audit
append-only + document hash") and ai-architecture.md §9 (Finding versioning)
— not a convention enforced by code review, but the only function that
knows how to compute the next version number or emit an event.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from shared.models import Case, ConflictRecord, DecisionPackage, Event, Finding
from shared.schemas import Actor, DecisionPackageIn, DecisionPackageOut, EventOut, FindingIn, FindingOut

# ---------------------------------------------------------------------------
# Finding write path
# ---------------------------------------------------------------------------

# Short codes used to mint human-readable finding_key values (F-FIN-001, ...).
# Extend this as new agents are added (Customer 360 / Industry in Phase 7).
AGENT_CODE = {
    "financial_analysis": "FIN",
    "policy_compliance": "POL",
    "collateral_legal": "COL",
    "customer_360": "C360",
    "industry_risk": "IND",
    "decision_synthesis": "DS",
}

# NFR-01 groundedness guard: a material (HIGH/CRITICAL) finding without any
# evidence_id must not be written — the caller should return NEED_DATA /
# INSUFFICIENT_EVIDENCE instead of fabricating a claim.
_MATERIAL_SEVERITIES = {"HIGH", "CRITICAL"}


class EvidenceRequiredError(ValueError):
    """Raised when a HIGH/CRITICAL finding has no evidence_ids (NFR-01)."""


def _next_finding_key(session: Session, case_id: str, agent_id: str) -> str:
    code = AGENT_CODE.get(agent_id, agent_id[:3].upper())
    prefix = f"F-{code}-"
    existing = session.execute(
        select(func.count(func.distinct(Finding.finding_key))).where(
            Finding.case_id == case_id, Finding.finding_key.like(f"{prefix}%")
        )
    ).scalar_one()
    return f"{prefix}{existing + 1:03d}"


def write_finding(
    session: Session,
    finding: FindingIn,
    *,
    finding_key: str | None = None,
    versions: dict[str, str] | None = None,
) -> FindingOut:
    """Insert a new Finding row.

    - `finding_key=None` mints a brand-new finding lineage (version=1).
    - `finding_key="F-COL-004"` appends the next version to an EXISTING
      lineage (Phase 4 challenge loop) — `finding.change_reason` should be
      set in that case; the prior row is never updated or deleted.
    """
    if finding.severity in _MATERIAL_SEVERITIES and not finding.evidence_ids:
        raise EvidenceRequiredError(
            f"Finding severity={finding.severity} requires evidence_ids "
            "(NFR-01) — return NEED_DATA/INSUFFICIENT_EVIDENCE instead of writing this."
        )

    if finding_key is None:
        finding_key = _next_finding_key(session, finding.case_id, finding.agent_id)
        version = 1
    else:
        current_max = session.execute(
            select(func.max(Finding.version)).where(Finding.finding_key == finding_key)
        ).scalar_one()
        if current_max is None:
            raise ValueError(f"finding_key {finding_key!r} does not exist yet — omit it to create v1")
        version = current_max + 1

    row = Finding(
        finding_key=finding_key,
        case_id=finding.case_id,
        agent_id=finding.agent_id,
        issue_key=finding.issue_key,
        claim_type=finding.claim_type,
        claim=finding.claim,
        stance=finding.stance,
        severity=finding.severity,
        evidence_ids=finding.evidence_ids,
        citations=[c.model_dump() for c in finding.citations],
        metrics=finding.metrics,
        confidence=finding.confidence,
        recommended_action=finding.recommended_action,
        version=version,
        change_reason=finding.change_reason,
    )
    session.add(row)
    session.flush()  # populate row.id / created_at before building FindingOut

    emit_event(
        session,
        case_id=finding.case_id,
        event_type="FINDING_WRITTEN",
        actor=Actor(type="AGENT", id=finding.agent_id),
        payload={"finding_key": finding_key, "version": version, "issue_key": finding.issue_key},
        versions=versions or {},
    )

    return FindingOut(
        **finding.model_dump(),
        finding_key=finding_key,
        version=version,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Decision write path — ai-architecture.md §10. Decision Synthesis is a
# worker like any other (writes via the same state layer as agents), NOT a
# side-effect tool — only the STATE TRANSITION to READY_FOR_REVIEW that
# follows goes through mcp-state (see worker/app/graph/decision.py).
# ---------------------------------------------------------------------------
def write_decision(session: Session, decision: DecisionPackageIn) -> DecisionPackageOut:
    row = DecisionPackage(
        case_id=decision.case_id,
        recommendation=decision.recommendation,
        requested_amount_vnd=decision.requested_amount_vnd,
        recommended_amount_vnd=decision.recommended_amount_vnd,
        recommended_tenor_months=decision.recommended_tenor_months,
        hard_gates=[g.model_dump() for g in decision.hard_gates],
        scores=[s.model_dump() for s in decision.scores],
        strengths=decision.strengths,
        risks=decision.risks,
        conditions_precedent=decision.conditions_precedent,
        dissent=decision.dissent,
        unresolved_questions=decision.unresolved_questions,
        policy_version=decision.policy_version,
        decision_matrix_version=decision.decision_matrix_version,
        version=1,
    )
    session.add(row)
    session.flush()

    emit_event(
        session,
        case_id=decision.case_id,
        event_type="DECISION_SYNTHESIZED",
        actor=Actor(type="AGENT", id="decision_synthesis"),
        payload={"decision_id": row.decision_id, "recommendation": decision.recommendation},
        versions={"decision_matrix_version": decision.decision_matrix_version or ""},
    )

    return DecisionPackageOut(
        decision_id=row.decision_id,
        case_id=decision.case_id,
        recommendation=decision.recommendation,
        requested_amount_vnd=decision.requested_amount_vnd,
        recommended_amount_vnd=decision.recommended_amount_vnd,
        recommended_tenor_months=decision.recommended_tenor_months,
        hard_gates=decision.hard_gates,
        scores=decision.scores,
        strengths=decision.strengths,
        risks=decision.risks,
        conditions_precedent=decision.conditions_precedent,
        dissent=decision.dissent,
        unresolved_questions=decision.unresolved_questions,
        policy_version=decision.policy_version,
        decision_matrix_version=decision.decision_matrix_version,
        version=1,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Audit event log — append-only (FR-12)
# ---------------------------------------------------------------------------
def emit_event(
    session: Session,
    *,
    case_id: str,
    event_type: str,
    actor: Actor,
    payload: dict[str, Any] | None = None,
    versions: dict[str, str] | None = None,
) -> EventOut:
    """Append one audit event. `seq` is assigned under a per-case Postgres
    advisory lock so concurrent writers (e.g. 3 expert agents in a FanOut,
    each emitting their own TOOL_CALL/FINDING_WRITTEN events) never collide
    on the same seq number for one case_id."""
    # hashtext() is a stable 32-bit hash Postgres ships built in; scoping the
    # lock to this case_id only serializes events for THIS case, not globally.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:case_id))"), {"case_id": case_id})

    next_seq = session.execute(
        select(func.coalesce(func.max(Event.seq), 0) + 1).where(Event.case_id == case_id)
    ).scalar_one()

    row = Event(
        case_id=case_id,
        seq=next_seq,
        event_type=event_type,
        actor=actor.model_dump(),
        payload=payload or {},
        versions=versions or {},
    )
    session.add(row)
    session.flush()

    return EventOut(
        event_id=row.event_id,
        case_id=case_id,
        seq=next_seq,
        event_type=event_type,
        actor=actor,
        timestamp=row.timestamp,
        payload=row.payload,
        versions=row.versions,
    )


# ---------------------------------------------------------------------------
# State machine — data-flow.md §2. Transitions are validated here, not left
# to whichever caller happens to update `cases.state` last.
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"INTAKE_VALIDATION"},
    "INTAKE_VALIDATION": {"NEED_INFO", "ANALYZING"},
    "NEED_INFO": {"INTAKE_VALIDATION"},
    "ANALYZING": {"CHALLENGE", "READY_FOR_REVIEW"},
    "CHALLENGE": {"READY_FOR_REVIEW"},
    "READY_FOR_REVIEW": {"ANALYZING", "NEED_INFO", "SUBMITTED_FOR_APPROVAL"},
    "SUBMITTED_FOR_APPROVAL": {"CONDITION_FULFILLMENT"},
    "CONDITION_FULFILLMENT": {"READY_FOR_DISBURSEMENT"},
    "READY_FOR_DISBURSEMENT": set(),  # terminal
}


class InvalidTransitionError(ValueError):
    pass


def transition_state(session: Session, *, case_id: str, new_state: str, actor: Actor, reason: str | None = None) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise ValueError(f"case {case_id!r} not found")

    allowed = ALLOWED_TRANSITIONS.get(case.state, set())
    if new_state not in allowed:
        raise InvalidTransitionError(
            f"cannot transition case {case_id} from {case.state!r} to {new_state!r} "
            f"(allowed: {sorted(allowed) or 'none — terminal state'})"
        )

    old_state = case.state
    case.state = new_state
    case.version += 1
    case.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()

    emit_event(
        session,
        case_id=case_id,
        event_type="STATE_TRANSITION",
        actor=actor,
        payload={"from": old_state, "to": new_state, "reason": reason},
    )
    return case
