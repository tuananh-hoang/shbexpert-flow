"""Shared helpers for expert agents — reading already-"OCR'd" data, and the
async/sync bridge that avoids a real deadlock found while testing Phase 3's
FanOut (see the long comment on `run_sync` below).

Per the user's constraint, no agent here ever touches OCR/extraction
logic; they only read ExtractedField rows a seed script (or, in a real
system, the Document Processing Pipeline) already wrote.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, TypeVar

from sqlalchemy import select

from shared.db import get_session
from shared.models import (
    Case,
    ChecklistCompletion,
    CollateralRegistry,
    CoOwnerRegistry,
    Document,
    ExtractedField,
    HaircutMatrix,
    LegalChecklistTemplate,
    LegalDocumentStore,
    OwnershipEncumbrance,
    RegulatoryReference,
)
from shared.schemas import Actor, FindingIn, FindingOut
from shared.state import write_finding

T = TypeVar("T")


async def run_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Runs a blocking (sync SQLAlchemy) call in a worker thread instead of
    directly on the asyncio event loop.

    Why this exists — a real deadlock, reproduced and diagnosed live during
    Phase 3 testing, not a theoretical concern:

    LangGraph's FanOut runs Financial/Policy/Collateral as concurrent
    coroutines on ONE event loop thread. Each agent opens a sync SQLAlchemy
    session, does a blocking read, then `await`s async I/O (an MCP tool
    call, an LLM completion) WHILE the transaction stays open, then later
    does a blocking write (`write_finding`, which takes a per-case Postgres
    advisory lock via `pg_advisory_xact_lock`). Financial writes TWO
    findings in the same session/transaction, so it holds that advisory
    lock from its first write clear through a second round of awaits.

    Sequence that deadlocked: Financial's session grabs the 'C06' advisory
    lock during its first write_finding, then awaits `calculate_coverage`
    for its second finding — control returns to the event loop, which runs
    Collateral's coroutine. Collateral's own write_finding tries to grab
    the SAME advisory lock and BLOCKS — but that block is a *synchronous*
    psycopg2 call, so it freezes the entire single-threaded event loop.
    Financial's pending async HTTP response (for `calculate_coverage`) can
    now never be processed, so Financial's session never commits, so the
    lock it holds is never released, so Collateral's blocking call waits
    forever. Confirmed via `pg_stat_activity`: two sessions "idle in
    transaction" holding locks mid-await, one session `active` stuck on
    `pg_advisory_xact_lock`, worker CPU at 0% (genuinely blocked, not busy).

    Fix: every DB read/write is now a short, self-contained sync function
    (opens a session, does ONE thing, commits, closes) executed via
    `asyncio.to_thread`. A blocking call now blocks its OWN OS thread, not
    the event loop — so other coroutines' pending async I/O keeps
    progressing, sessions commit promptly, and advisory locks are never
    held across an await boundary.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------------------
# Sync helpers — each opens and closes its OWN session. Call these only via
# run_sync() from agent code, never directly from an async function body.
# ---------------------------------------------------------------------------
def read_extracted_fields_sync(case_id: str) -> dict[str, dict]:
    """Returns {field_key: {"value": ..., "evidence_id": field_id}} for
    every ExtractedField belonging to any Document of this case."""
    with get_session() as session:
        rows = session.execute(
            select(ExtractedField, Document.document_id)
            .join(Document, ExtractedField.document_id == Document.document_id)
            .where(Document.case_id == case_id)
        ).all()
        return {
            row.ExtractedField.field_key: {
                "value": row.ExtractedField.value,
                "evidence_id": row.ExtractedField.field_id,
            }
            for row in rows
        }


def read_requested_facility_sync(case_id: str) -> dict:
    """Returns Case.requested_facility as a plain dict — deliberately NOT
    the ORM object, so nothing outside this function ever touches an
    instance whose session has already closed."""
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id!r} not found")
        return dict(case.requested_facility)


def read_case_customer_id_sync(case_id: str) -> str:
    """Returns Case.customer_id — used as the identity to cross-check
    against collateral_registry.owner_id in validate_ownership_sync."""
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id!r} not found")
        return case.customer_id


def write_finding_sync(
    finding: FindingIn,
    *,
    finding_key: str | None = None,
    versions: dict[str, str] | None = None,
) -> FindingOut:
    with get_session() as session:
        return write_finding(session, finding, finding_key=finding_key, versions=versions)


def emit_event_sync(case_id: str, event_type: str, actor: Actor, payload: dict | None = None) -> None:
    from shared.state import emit_event

    with get_session() as session:
        emit_event(session, case_id=case_id, event_type=event_type, actor=actor, payload=payload or {})


# ---------------------------------------------------------------------------
# Collateral & Legal domain reads — direct shared.db reads, same rationale
# as read_extracted_fields_sync above (plain relational facts/reference
# data, no computation and no external boundary, so no MCP tool needed —
# see shared/models.py's "Collateral & Legal domain" section and the plan
# this implements). Called via run_sync from worker/app/agents/collateral.py.
# ---------------------------------------------------------------------------
def validate_ownership_sync(collateral_id: str, customer_id: str) -> dict:
    """Cross-checks collateral_registry/ownership_encumbrance/
    legal_document_store/co_owner_registry for one collateral item —
    validate_ownership's full logic. Returns an OwnershipFinding-shaped
    dict plus `_evidence_ids` (row ids that grounded the claim, so the
    caller can populate FindingIn.evidence_ids without re-deriving them)."""
    with get_session() as session:
        registry = session.get(CollateralRegistry, collateral_id)
        encumbrances = session.execute(
            select(OwnershipEncumbrance).where(OwnershipEncumbrance.collateral_id == collateral_id)
        ).scalars().all()
        legal_docs = session.execute(
            select(LegalDocumentStore).where(LegalDocumentStore.collateral_id == collateral_id)
        ).scalars().all()
        co_owners = session.execute(
            select(CoOwnerRegistry).where(CoOwnerRegistry.collateral_id == collateral_id)
        ).scalars().all()

        ownership_verified = registry is not None and registry.owner_id == customer_id
        active_encumbrances = [e for e in encumbrances if e.status == "ACTIVE"]
        encumbrance_found = len(active_encumbrances) > 0
        missing_documents = [d.doc_type for d in legal_docs if d.verification_status != "VERIFIED"]
        unconfirmed_co_owners = [c for c in co_owners if c.consent_status != "CONFIRMED"]
        co_owner_consent_required = len(unconfirmed_co_owners) > 0

        legal_gap: list[str] = []
        if registry is None:
            legal_gap.append("Chưa có hồ sơ đăng ký TSBĐ (collateral_registry) cho collateral_id này")
        elif not ownership_verified:
            legal_gap.append("Chủ sở hữu đăng ký không khớp với khách vay/bên bảo lãnh")
        for e in active_encumbrances:
            legal_gap.append(f"TSBĐ đang bị {e.encumbrance_type} tại {e.encumbrance_holder or 'bên thứ ba'}")
        if missing_documents:
            legal_gap.append(f"Giấy tờ chưa xác minh: {', '.join(missing_documents)}")
        if co_owner_consent_required:
            legal_gap.append(f"Thiếu xác nhận đồng ý của {len(unconfirmed_co_owners)} đồng sở hữu")

        confidence_score = 100
        if registry is None or not ownership_verified:
            confidence_score -= 40
        if encumbrance_found:
            confidence_score -= 30
        if missing_documents:
            confidence_score -= 20
        if co_owner_consent_required:
            confidence_score -= 10
        confidence_score = max(confidence_score, 0)

        evidence_ids = (
            ([registry.collateral_id] if registry else [])
            + [e.id for e in active_encumbrances]
            + [d.doc_id for d in legal_docs if d.doc_type in missing_documents]
            + [c.id for c in unconfirmed_co_owners]
        )

        return {
            "collateral_id": collateral_id,
            "registry_found": registry is not None,
            "ownership_verified": ownership_verified,
            "encumbrance_found": encumbrance_found,
            "encumbrance_details": [
                {"encumbrance_type": e.encumbrance_type, "encumbrance_holder": e.encumbrance_holder, "status": e.status}
                for e in active_encumbrances
            ],
            "missing_documents": missing_documents,
            "co_owner_consent_required": co_owner_consent_required,
            "legal_gap": legal_gap,
            "confidence_score": confidence_score,
            "_evidence_ids": evidence_ids,
        }


def read_haircut_rate_sync(collateral_type: str) -> float | None:
    """Reads the reference haircut_matrix table (seeded once, shared across
    every case — scripts/seed_collateral_reference.py). Kept as a plain
    read so calculate_collateral_coverage (mcp-deterministic) stays a pure
    function that never touches Postgres — the agent looks up haircut_rate
    itself and passes it as a tool argument."""
    with get_session() as session:
        row = session.execute(
            select(HaircutMatrix).where(HaircutMatrix.collateral_type == collateral_type)
        ).scalars().first()
        return row.haircut_rate if row else None


def read_checklist_items_sync(collateral_id: str, collateral_type: str) -> list[dict]:
    """Joins legal_checklist_template -> regulatory_reference (structured
    citation) and checklist_completion (per-case status) for every
    checklist item matching `collateral_type`. Combined in
    collateral.py with search_legal_checklist's semantic hits (matched by
    `checklist_id`) to build checklist_items[]/condition_precedent[]."""
    with get_session() as session:
        templates = session.execute(
            select(LegalChecklistTemplate, RegulatoryReference)
            .outerjoin(RegulatoryReference, LegalChecklistTemplate.legal_reference == RegulatoryReference.reference_id)
            .where(LegalChecklistTemplate.collateral_type == collateral_type)
        ).all()
        completions = {
            c.checklist_id: c
            for c in session.execute(
                select(ChecklistCompletion).where(ChecklistCompletion.collateral_id == collateral_id)
            ).scalars().all()
        }

        items = []
        for template, reg_ref in templates:
            completion = completions.get(template.checklist_id)
            items.append(
                {
                    "checklist_id": template.checklist_id,
                    "required_document": template.required_document,
                    "is_mandatory": template.is_mandatory,
                    "legal_reference": f"{reg_ref.law_name} {reg_ref.article or ''}".strip() if reg_ref else None,
                    "status": completion.completion_status if completion else "missing",
                    "completion_id": completion.id if completion else None,
                }
            )
        return items


def unwrap_mcp_result(result):
    """FastMCP tools return a LIST of content blocks over the wire
    (`[{"type": "text", "text": "<json string>", "id": "..."}]`), not a
    pre-parsed dict — verified empirically in Phase 2/3 smoke tests. Some
    future langchain-mcp-adapters version might start auto-parsing
    structured content, so a bare dict is handled too."""
    if isinstance(result, dict):
        return result
    return json.loads(result[0]["text"])
