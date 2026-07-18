"""Case endpoints — the only surface `web` talks to (overview.md §4: "web
không gọi thẳng postgres/redis — mọi thứ qua api"). Phase 6 adds the reads
the dashboard needs: latest findings, conflicts, decision package,
evidence resolution (ExtractedField -> presigned document URL), and the
audit event log. RBAC/field-level filtering is still a TODO — every field
is visible to every caller for now, noted rather than silently assumed.
"""
from __future__ import annotations

import json
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select

from shared.constants import REQUIRED_DOC_TYPES
from shared.db import get_session
from shared.models import Case, ConflictRecord, DecisionPackage, Document, Event, ExtractedField, Finding
from shared.queue import ANALYZE_QUEUE, progress_channel
from shared.schemas import Actor
from shared.state import InvalidTransitionError, emit_event, transition_state
from shared.storage import get_object_bytes, presigned_url
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/cases", tags=["cases"])

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _finding_dict(f: Finding) -> dict:
    return {
        "display_id": f.display_id,
        "finding_key": f.finding_key,
        "agent_id": f.agent_id,
        "issue_key": f.issue_key,
        "claim_type": f.claim_type,
        "claim": f.claim,
        "stance": f.stance,
        "severity": f.severity,
        "confidence": f.confidence,
        "evidence_ids": f.evidence_ids,
        "citations": f.citations,
        "metrics": f.metrics,
        "recommended_action": f.recommended_action,
        "version": f.version,
        "change_reason": f.change_reason,
        "created_at": f.created_at.isoformat(),
    }


def _latest_findings(session, case_id: str) -> list[Finding]:
    findings = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
    latest: dict[str, Finding] = {}
    for f in findings:
        cur = latest.get(f.finding_key)
        if cur is None or f.version > cur.version:
            latest[f.finding_key] = f
    return sorted(latest.values(), key=lambda f: f.created_at)


@router.get("")
def list_cases() -> dict:
    """Application Queue data source (FE_flow.jpeg Screen 0) — one row per
    Case with just enough to render a queue list + status badge. Full
    detail (findings/conflicts/decision) is only fetched once a specific
    case is opened, via GET /{case_id}."""
    with get_session() as session:
        cases = session.execute(select(Case).order_by(Case.updated_at.desc())).scalars().all()
        case_ids_with_findings = {
            row[0] for row in session.execute(select(Finding.case_id).distinct()).all()
        }
        return {
            "cases": [
                {
                    "case_id": c.case_id,
                    "customer_id": c.customer_id,
                    "product": c.product,
                    "state": c.state,
                    "requested_facility": c.requested_facility,
                    "updated_at": c.updated_at.isoformat(),
                    "has_findings": c.case_id in case_ids_with_findings,
                }
                for c in cases
            ]
        }


@router.post("/{case_id}/analyze")
async def analyze_case(case_id: str) -> dict:
    with get_session() as session:
        if session.get(Case, case_id) is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")

    r = aioredis.from_url(REDIS_URL)
    try:
        await r.lpush(ANALYZE_QUEUE, json.dumps({"case_id": case_id}))
    finally:
        await r.aclose()
    return {"status": "queued", "case_id": case_id}


@router.get("/{case_id}")
def get_case(case_id: str) -> dict:
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")

        findings = _latest_findings(session, case_id)

        conflicts = session.execute(select(ConflictRecord).where(ConflictRecord.case_id == case_id)).scalars().all()

        decision = (
            session.execute(
                select(DecisionPackage)
                .where(DecisionPackage.case_id == case_id)
                .order_by(DecisionPackage.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        documents = session.execute(select(Document).where(Document.case_id == case_id)).scalars().all()

        return {
            "case_id": case.case_id,
            "customer_id": case.customer_id,
            "product": case.product,
            "state": case.state,
            "version": case.version,
            "requested_facility": case.requested_facility,
            "documents": [{"document_id": d.document_id, "doc_type": d.doc_type} for d in documents],
            "required_doc_types": sorted(REQUIRED_DOC_TYPES),
            "findings": [_finding_dict(f) for f in findings],
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "issue_key": c.issue_key,
                    "round": c.round,
                    "status": c.status,
                    "source_findings": c.source_findings,
                    "targeted_questions": c.targeted_questions,
                }
                for c in conflicts
            ],
            "decision": (
                {
                    "decision_id": decision.decision_id,
                    "recommendation": decision.recommendation,
                    "requested_amount_vnd": decision.requested_amount_vnd,
                    "recommended_amount_vnd": decision.recommended_amount_vnd,
                    "recommended_tenor_months": decision.recommended_tenor_months,
                    "hard_gates": decision.hard_gates,
                    "scores": decision.scores,
                    "strengths": decision.strengths,
                    "risks": decision.risks,
                    "conditions_precedent": decision.conditions_precedent,
                    "dissent": decision.dissent,
                    "policy_version": decision.policy_version,
                    "decision_matrix_version": decision.decision_matrix_version,
                }
                if decision
                else None
            ),
        }


@router.get("/{case_id}/findings/{finding_key}/history")
def get_finding_history(case_id: str, finding_key: str) -> dict:
    """Full version history of one finding lineage — the "decision trace"
    the Explainable_AI_Interaction_Design.md drawer wants (v1 kept
    alongside v2/v3, never overwritten)."""
    with get_session() as session:
        rows = (
            session.execute(
                select(Finding)
                .where(Finding.case_id == case_id, Finding.finding_key == finding_key)
                .order_by(Finding.version)
            )
            .scalars()
            .all()
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"no finding {finding_key!r} on case {case_id!r}")
        return {"finding_key": finding_key, "versions": [_finding_dict(f) for f in rows]}


@router.get("/{case_id}/evidence")
def get_evidence(case_id: str, ids: str = Query(..., description="comma-separated ExtractedField ids")) -> dict:
    """Resolves evidence_ids (ExtractedField primary keys) to displayable
    evidence: the field's value/confidence/page/bbox plus a presigned URL
    to the source document — what the Evidence Viewer opens
    (Explainable_AI_Interaction_Design.md Screen 3)."""
    field_ids = [i for i in ids.split(",") if i]
    with get_session() as session:
        rows = session.execute(select(ExtractedField).where(ExtractedField.field_id.in_(field_ids))).scalars().all()
        results = []
        for field in rows:
            doc = session.get(Document, field.document_id)
            results.append(
                {
                    "field_id": field.field_id,
                    "field_key": field.field_key,
                    "value": field.value,
                    "confidence": field.confidence,
                    "page": field.page,
                    "bbox": field.bbox,
                    "document_id": doc.document_id if doc else None,
                    "doc_type": doc.doc_type if doc else None,
                    "document_url": presigned_url(doc.minio_key) if doc else None,
                    # /api prefix matches next.config.mjs's rewrite ("web"
                    # never talks to `api` directly) — every other web/app/
                    # lib/api.ts call already goes through this same prefix.
                    "viewer_url": f"/api/cases/{case_id}/documents/{doc.document_id}/file" if doc else None,
                }
            )
        return {"evidence": results}


@router.get("/{case_id}/documents/{document_id}/file")
def get_document_file(case_id: str, document_id: str):
    """Same-origin PDF stream for the in-app Evidence Viewer (react-pdf) —
    proxies MinIO through api rather than handing the browser a presigned
    MinIO URL directly, so react-pdf's fetch of the PDF bytes never hits
    a cross-origin request that would need MinIO bucket CORS configured.
    `document_url` (presigned, direct-to-MinIO) is kept as the "mở tài
    liệu gốc" download-in-new-tab fallback; this is only for the embedded
    viewer."""
    with get_session() as session:
        doc = session.get(Document, document_id)
        if doc is None or doc.case_id != case_id:
            raise HTTPException(status_code=404, detail=f"document {document_id!r} not found on case {case_id!r}")
        data = get_object_bytes(doc.minio_key)
        return Response(content=data, media_type="application/pdf")


@router.get("/{case_id}/audit")
def get_audit(case_id: str) -> dict:
    """Audit tab data source — reads the append-only events table directly
    (data-flow.md §10: "Audit tab đọc thẳng event log, không phải log ứng
    dụng")."""
    with get_session() as session:
        rows = session.execute(select(Event).where(Event.case_id == case_id).order_by(Event.seq)).scalars().all()
        return {
            "events": [
                {
                    "seq": e.seq,
                    "event_type": e.event_type,
                    "actor": e.actor,
                    "timestamp": e.timestamp.isoformat(),
                    "payload": e.payload,
                    "versions": e.versions,
                }
                for e in rows
            ]
        }


class DecisionActionRequest(BaseModel):
    action: str  # accept | edit | rerun | return | override
    reason: str | None = None


_ACTION_TRANSITIONS = {
    "accept": "SUBMITTED_FOR_APPROVAL",
    "override": "SUBMITTED_FOR_APPROVAL",
    "return": "NEED_INFO",
    "rerun": "ANALYZING",
    # "edit" has no state transition — see below.
}
_REASON_REQUIRED_ACTIONS = {"edit", "override"}  # FR-11 / AS-05


@router.post("/{case_id}/decision/action")
async def decision_action(case_id: str, body: DecisionActionRequest) -> dict:
    """Credit Officer actions (data-flow.md §8): accept / edit / rerun /
    return / override. Edit and override REQUIRE a reason (FR-11, AS-05) —
    enforced server-side, not just as a client-side form validation that a
    direct API call could skip."""
    if body.action not in {"accept", "edit", "rerun", "return", "override"}:
        raise HTTPException(status_code=400, detail=f"unknown action {body.action!r}")
    if body.action in _REASON_REQUIRED_ACTIONS and not body.reason:
        raise HTTPException(status_code=400, detail=f"action {body.action!r} requires a reason (FR-11)")

    with get_session() as session:
        if session.get(Case, case_id) is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")

        emit_event(
            session,
            case_id=case_id,
            event_type="CO_ACTION",
            actor=Actor(type="USER", id="credit_officer_demo"),
            payload={"action": body.action, "reason": body.reason},
        )

        new_state = _ACTION_TRANSITIONS.get(body.action)
        if new_state:
            try:
                case = transition_state(
                    session,
                    case_id=case_id,
                    new_state=new_state,
                    actor=Actor(type="USER", id="credit_officer_demo"),
                    reason=body.reason,
                )
            except InvalidTransitionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            result_state = case.state
        else:
            result_state = session.get(Case, case_id).state

    if body.action == "rerun":
        r = aioredis.from_url(REDIS_URL)
        try:
            await r.lpush(ANALYZE_QUEUE, json.dumps({"case_id": case_id}))
        finally:
            await r.aclose()

    return {"case_id": case_id, "action": body.action, "state": result_state}


@router.get("/{case_id}/stream")
async def stream_case(case_id: str) -> EventSourceResponse:
    """SSE endpoint `web` opens to watch a running analyze job. Forwards
    whatever `worker` publishes on the per-case Redis pub/sub channel —
    api never generates progress events itself, it's a pure relay."""

    async def event_generator():
        r = aioredis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(progress_channel(case_id))
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield {"event": "progress", "data": message["data"].decode()}
        finally:
            await pubsub.unsubscribe(progress_channel(case_id))
            await r.aclose()

    return EventSourceResponse(event_generator())
