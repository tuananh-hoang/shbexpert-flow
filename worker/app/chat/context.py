"""Case Snapshot Context for the Chat Orchestrator (ai-architecture_v2.md
§11.8) — loads everything a chat turn needs in ONE read: case identity,
every agent's LATEST findings (grouped by agent_id — same "one card per
agent" grouping web/app/components/AgentTraceCard.tsx does on the
frontend), the current DecisionPackage, open conflicts, and recent thread
history.

Read directly via shared.db, same "direct read, not MCP" principle
worker/app/agents/common.py already uses for reference/relational data —
a chat turn does no tool-calling, no side effects, so there is nothing
here for an MCP allowlist to gate.
"""
from __future__ import annotations

from sqlalchemy import select

from shared.db import get_session
from shared.models import Case, ChatMessage, ConflictRecord, DecisionPackage, Finding


def load_case_snapshot_sync(case_id: str) -> dict:
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id!r} not found")

        findings = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
        latest: dict[str, Finding] = {}
        for f in findings:
            cur = latest.get(f.finding_key)
            if cur is None or f.version > cur.version:
                latest[f.finding_key] = f

        by_agent: dict[str, list[dict]] = {}
        for f in latest.values():
            by_agent.setdefault(f.agent_id, []).append(
                {
                    "issue_key": f.issue_key,
                    "claim": f.claim,
                    "stance": f.stance,
                    "severity": f.severity,
                    "metrics": f.metrics,
                    "display_id": f.display_id,
                }
            )

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

        conflicts = session.execute(select(ConflictRecord).where(ConflictRecord.case_id == case_id)).scalars().all()

        return {
            "case_id": case.case_id,
            "product": case.product,
            "state": case.state,
            "requested_facility": case.requested_facility,
            "findings_by_agent": by_agent,
            "decision": (
                {
                    "recommendation": decision.recommendation,
                    "scores": decision.scores,
                    "hard_gates": decision.hard_gates,
                    "conditions_precedent": decision.conditions_precedent,
                }
                if decision
                else None
            ),
            "conflicts": [{"issue_key": c.issue_key, "status": c.status, "round": c.round} for c in conflicts],
        }


def load_recent_messages_sync(thread_id: str, limit: int = 10) -> list[dict]:
    with get_session() as session:
        rows = (
            session.execute(
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread_id)
                .order_by(ChatMessage.seq.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]
