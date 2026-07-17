"""Conflict Detector — ai-architecture.md §9.2. A pure function (hàm
thuần), NOT an LLM call: groups the LATEST version of each finding by
issue_key, flags groups where agents disagree (different `stance`).

Runs once after the initial FanOut, and again after every challenge round.
`round` lives on the ConflictRecord row itself (not graph state) so it
survives a worker crash/restart mid-challenge (NFR-03) — see
ai-architecture.md §9.2 step 5 "Dừng có kiểm soát" and the bit about
`round` being "một biến đếm ở cạnh Challenge → Detect, không phải câu chữ
trong prompt": here it's a column checked by pure Python, not something an
LLM is trusted to count correctly.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from shared.db import get_session
from shared.models import ConflictRecord, Finding
from shared.schemas import Actor
from shared.state import emit_event

MAX_ROUNDS = 2

# Which agent owns the "more authoritative" evidence for a given issue_key —
# ai-architecture.md §9.2 step 2: "Chọn agent sở hữu bằng chứng gốc... Không
# broadcast." Only ONE agent is asked, never the whole council. Extend this
# mapping as more conflict-prone issue_keys are added in later phases.
CHALLENGE_TARGET_AGENT = {
    "COLLATERAL_COVERAGE": "collateral_legal",
}


def _latest_findings_by_issue(session, case_id: str) -> dict[str, list[Finding]]:
    findings = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
    latest_by_key: dict[str, Finding] = {}
    for f in findings:
        existing = latest_by_key.get(f.finding_key)
        if existing is None or f.version > existing.version:
            latest_by_key[f.finding_key] = f
    by_issue: dict[str, list[Finding]] = defaultdict(list)
    for f in latest_by_key.values():
        by_issue[f.issue_key].append(f)
    return by_issue


def detect_and_update_conflicts_sync(case_id: str) -> bool:
    """One detect pass. Returns True if at least one conflict still needs
    another challenge round (caller should route to "challenge"), False if
    the case is clear to proceed (every issue_key agrees, or every
    disagreement has hit MAX_ROUNDS and is now UNRESOLVED with dissent
    preserved — ai-architecture.md §9.4: "Dissent được bảo toàn, không bị
    san phẳng")."""
    with get_session() as session:
        by_issue = _latest_findings_by_issue(session, case_id)
        needs_challenge = False

        for issue_key, group in by_issue.items():
            stances = {f.stance for f in group}
            disagreement = len(group) >= 2 and len(stances) > 1
            source_findings = [f.display_id for f in group]

            existing = session.execute(
                select(ConflictRecord).where(ConflictRecord.case_id == case_id, ConflictRecord.issue_key == issue_key)
            ).scalar_one_or_none()

            if not disagreement:
                if existing is not None and existing.status == "OPEN":
                    existing.status = "RESOLVED"
                    existing.source_findings = source_findings
                    session.flush()
                    emit_event(
                        session,
                        case_id=case_id,
                        event_type="CONFLICT_RESOLVED",
                        actor=Actor(type="SYSTEM", id="conflict_detector"),
                        payload={"issue_key": issue_key, "conflict_id": existing.conflict_id},
                    )
                continue

            if existing is None:
                existing = ConflictRecord(
                    case_id=case_id,
                    issue_key=issue_key,
                    source_findings=source_findings,
                    targeted_questions=[],
                    round=0,
                    status="OPEN",
                )
                session.add(existing)
                session.flush()
                emit_event(
                    session,
                    case_id=case_id,
                    event_type="CONFLICT_DETECTED",
                    actor=Actor(type="SYSTEM", id="conflict_detector"),
                    payload={"issue_key": issue_key, "conflict_id": existing.conflict_id, "stances": sorted(stances)},
                )
            elif existing.status != "OPEN":
                continue  # already finalized (UNRESOLVED) in an earlier pass — never reopen
            else:
                existing.source_findings = source_findings

            if existing.round >= MAX_ROUNDS:
                existing.status = "UNRESOLVED"
                session.flush()
                emit_event(
                    session,
                    case_id=case_id,
                    event_type="CONFLICT_UNRESOLVED",
                    actor=Actor(type="SYSTEM", id="conflict_detector"),
                    payload={"issue_key": issue_key, "conflict_id": existing.conflict_id, "dissent": source_findings},
                )
            else:
                existing.round += 1
                session.flush()
                needs_challenge = True

        return needs_challenge


def get_open_conflicts_sync(case_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.execute(
            select(ConflictRecord).where(ConflictRecord.case_id == case_id, ConflictRecord.status == "OPEN")
        ).scalars().all()
        return [{"conflict_id": r.conflict_id, "issue_key": r.issue_key, "round": r.round} for r in rows]


def record_targeted_question_sync(conflict_id: str, to_agent: str, question: str, required_evidence: list[str]) -> None:
    with get_session() as session:
        conflict = session.get(ConflictRecord, conflict_id)
        conflict.targeted_questions = [
            *conflict.targeted_questions,
            {"to_agent": to_agent, "question": question, "required_evidence": required_evidence},
        ]
        session.flush()
        emit_event(
            session,
            case_id=conflict.case_id,
            event_type="TARGETED_QUESTION_SENT",
            actor=Actor(type="SYSTEM", id="orchestrator"),
            payload={"conflict_id": conflict_id, "to_agent": to_agent, "question": question},
        )


def get_latest_finding_key_sync(case_id: str, agent_id: str, issue_key: str) -> str:
    with get_session() as session:
        rows = session.execute(
            select(Finding.finding_key)
            .where(Finding.case_id == case_id, Finding.agent_id == agent_id, Finding.issue_key == issue_key)
            .limit(1)
        ).first()
        if rows is None:
            raise ValueError(f"no existing finding for agent={agent_id!r} issue_key={issue_key!r} on case {case_id!r}")
        return rows[0]
