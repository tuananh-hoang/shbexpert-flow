"""LangGraph graph — Plan -> FanOut(Financial, Policy, Collateral) -> Detect
-> Challenge (loop, max 2 rounds) -> END.

Matches ai-architecture.md §4: node = a resumable/checkpointed unit; state
diagram ANALYZING -> CHALLENGE -> READY_FOR_REVIEW. The three expert nodes
run as parallel branches from "plan" and all converge at "detect" (a real
node now, not implicit END) so conflict detection runs exactly once after
every FanOut/Challenge round.

The round limit is a graph EDGE CONDITION (`_route_after_detect` reading
`ConflictRecord.round` from Postgres), not a prompt instruction — see
conflict.py's docstring and ai-architecture.md §4: "Phanh nằm trong graph,
không nằm trong prompt."

`findings_written` is `Annotated[list[str], operator.add]` — REQUIRED for
concurrent branches that all update the same state key. Without a reducer,
LangGraph raises on the first attempt to merge two branches' updates to
the same field; `operator.add` tells it "concatenate the lists" instead.
"""
from __future__ import annotations

import operator
import re
from typing import Annotated, TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from app.progress import publish_progress
from shared.db import DATABASE_URL

import os

# .setup() below is DDL (CREATE TABLE checkpoints/checkpoint_writes/...) —
# `shbapp` (what DATABASE_URL/shared.db connects as) deliberately has no
# CREATE on schema public (see postgres/init/01-init-app-role.sh), so setup
# must run via the admin connection. Once the tables exist, the app's
# default-privilege grant covers them automatically (they were created by
# shbuser, the role that grant is scoped to) and normal get/put calls work
# fine over the regular least-privilege DATABASE_URL.
ADMIN_DATABASE_URL = os.environ.get("ADMIN_DATABASE_URL", DATABASE_URL)


def _psycopg_dsn(sqlalchemy_url: str) -> str:
    """AsyncPostgresSaver uses psycopg3, which wants a plain `postgresql://`
    DSN — SQLAlchemy's `postgresql+psycopg2://` dialect prefix isn't valid
    there, so strip it rather than maintaining a second DSN by hand."""
    return re.sub(r"^postgresql\+psycopg2://", "postgresql://", sqlalchemy_url)


class CaseGraphState(TypedDict):
    case_id: str
    as_of_date: str
    findings_written: Annotated[list[str], operator.add]


async def _plan_node(state: CaseGraphState) -> dict:
    """Orchestrator's Plan step — reads case metadata needed by every
    downstream agent (as_of_date for RAG version-filtering) so each expert
    node doesn't have to re-query it independently. No credit judgment
    happens here (ai-architecture.md §4: "Orchestrator không đưa nhận định
    tín dụng")."""
    from app.agents.common import read_requested_facility_sync, run_sync

    requested_facility = await run_sync(read_requested_facility_sync, state["case_id"])
    as_of_date = requested_facility.get("as_of_date", "2026-01-01") + "T00:00:00Z"
    return {"as_of_date": as_of_date}


async def _financial_node(state: CaseGraphState) -> dict:
    from app.agents.financial import run_financial_agent

    findings = await run_financial_agent(state["case_id"])
    return {"findings_written": [f.display_id for f in findings]}


async def _policy_node(state: CaseGraphState) -> dict:
    from app.agents.policy import run_policy_agent

    finding = await run_policy_agent(state["case_id"], state["as_of_date"])
    return {"findings_written": [finding.display_id]}


async def _collateral_node(state: CaseGraphState) -> dict:
    from app.agents.collateral import run_collateral_agent

    finding = await run_collateral_agent(state["case_id"], state["as_of_date"])
    return {"findings_written": [finding.display_id]}


async def _detect_node(state: CaseGraphState) -> dict:
    """Conflict Detector (ai-architecture.md §9.2) — a pure function, not
    an LLM call. Runs after the initial FanOut and after every challenge
    round; ConflictRecord.round in Postgres is the single source of truth
    for how many rounds have happened, so a worker restart mid-challenge
    resumes correctly instead of losing count."""
    from app.agents.common import run_sync
    from app.graph.conflict import detect_and_update_conflicts_sync

    await run_sync(detect_and_update_conflicts_sync, state["case_id"])
    return {}


async def _challenge_node(state: CaseGraphState) -> dict:
    """Orchestrator sends a targeted question to the SPECIFIC agent that
    owns the more authoritative evidence for each open conflict — never a
    broadcast to the whole council (ai-architecture.md §9.2 step 2)."""
    from app.agents.collateral import run_collateral_agent
    from app.agents.common import run_sync
    from app.graph.conflict import (
        CHALLENGE_TARGET_AGENT,
        get_latest_finding_key_sync,
        get_open_conflicts_sync,
        record_targeted_question_sync,
    )

    open_conflicts = await run_sync(get_open_conflicts_sync, state["case_id"])
    new_finding_ids: list[str] = []

    for conflict in open_conflicts:
        target_agent = CHALLENGE_TARGET_AGENT.get(conflict["issue_key"])
        if target_agent != "collateral_legal":
            continue  # no other issue_key -> agent mapping implemented yet

        question = (
            f"Coverage ratio của bạn khác với Financial Agent trên cùng issue "
            f"{conflict['issue_key']}. Vui lòng xác nhận lại kết luận, có tính "
            f"đến thời hạn hiệu lực của chứng thư định giá."
        )
        await run_sync(
            record_targeted_question_sync,
            conflict["conflict_id"],
            target_agent,
            question,
            ["valuation_expiry_date", "legal_checklist"],
        )
        existing_key = await run_sync(
            get_latest_finding_key_sync, state["case_id"], target_agent, conflict["issue_key"]
        )
        finding = await run_collateral_agent(
            state["case_id"],
            state["as_of_date"],
            finding_key=existing_key,
            change_reason=f"Trả lời targeted question ở vòng {conflict['round']} (conflict_id={conflict['conflict_id']}).",
            targeted_question=question,
        )
        new_finding_ids.append(finding.display_id)

    return {"findings_written": new_finding_ids}


async def _synthesize_node(state: CaseGraphState) -> dict:
    """Decision Synthesis (ai-architecture.md §5.7) — hard gates then
    scorecard, writes a DecisionPackage via the normal state layer. Does
    NOT transition case state itself; that's _transition_node's job, via
    mcp-state (the only side-effect tool call in this whole pipeline)."""
    from app.agents.common import run_sync
    from app.graph.decision import synthesize_decision_sync

    decision = await run_sync(synthesize_decision_sync, state["case_id"])
    return {"findings_written": [f"DECISION:{decision['recommendation']}"]}


async def _transition_node(state: CaseGraphState) -> dict:
    """The ONLY state-changing tool call in this pipeline — routed through
    mcp-state, which itself has no DB access and only forwards to api's
    state layer (see mcp-state/app/server.py). Expert agents have no
    client configured for mcp-state at all; only this graph node does."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from app.config import MCP_STATE_URL

    client = MultiServerMCPClient({"state": {"url": MCP_STATE_URL, "transport": "streamable_http"}})
    tools = {t.name: t for t in await client.get_tools()}
    await tools["update_case_status"].ainvoke(
        {
            "case_id": state["case_id"],
            "new_state": "READY_FOR_REVIEW",
            "reason": "Decision Synthesis hoàn tất — DecisionPackage đã ghi.",
        }
    )
    return {}


# Human-readable label per node — this IS the "thinking" trace the
# Analyzing screen renders (frontend-flow plan Phase 2), not a guessed
# animation: each label is published exactly when the real node it
# describes actually starts/finishes running.
STEP_LABELS: dict[str, str] = {
    "plan": "Đang đọc hồ sơ khách hàng",
    "financial": "Financial Agent đang phân tích năng lực tài chính",
    "policy": "Policy Agent đang tra cứu chính sách",
    "collateral": "Collateral Agent đang thẩm định tài sản đảm bảo",
    "detect": "Đang đối chiếu nhận định giữa các agent",
    "challenge": "Phát hiện mâu thuẫn — đang hỏi lại agent liên quan",
    "synthesize": "Đang tổng hợp quyết định tín dụng",
    "transition": "Đang cập nhật trạng thái hồ sơ",
}


def _with_progress(step_id: str, node_fn):
    """Wraps a node so it publishes step_started/step_completed around the
    REAL call — the three expert nodes run concurrently in one LangGraph
    superstep, so their step_started events land on the wire nearly
    simultaneously, same as the actual FanOut, never a fake sequential
    animation."""

    async def wrapped(state: CaseGraphState) -> dict:
        await publish_progress(state["case_id"], {"type": "step_started", "step": step_id, "label": STEP_LABELS[step_id]})
        try:
            result = await node_fn(state)
        except Exception:
            await publish_progress(state["case_id"], {"type": "step_failed", "step": step_id, "label": STEP_LABELS[step_id]})
            raise
        await publish_progress(state["case_id"], {"type": "step_completed", "step": step_id, "label": STEP_LABELS[step_id]})
        return result

    return wrapped


def _route_after_detect(state: CaseGraphState) -> str:
    """The round limit lives in the graph edge, not a prompt — reads
    ConflictRecord rows fresh from Postgres rather than trusting anything
    an LLM might have said about how many rounds are left."""
    from app.graph.conflict import get_open_conflicts_sync

    open_conflicts = get_open_conflicts_sync(state["case_id"])
    return "challenge" if open_conflicts else "done"


def _build_uncompiled_graph() -> StateGraph:
    graph = StateGraph(CaseGraphState)
    graph.add_node("plan", _with_progress("plan", _plan_node))
    graph.add_node("financial", _with_progress("financial", _financial_node))
    graph.add_node("policy", _with_progress("policy", _policy_node))
    graph.add_node("collateral", _with_progress("collateral", _collateral_node))
    graph.add_node("detect", _with_progress("detect", _detect_node))
    graph.add_node("challenge", _with_progress("challenge", _challenge_node))
    graph.add_node("synthesize", _with_progress("synthesize", _synthesize_node))
    graph.add_node("transition", _with_progress("transition", _transition_node))

    graph.set_entry_point("plan")
    # FanOut: three parallel branches from Plan (ai-architecture.md §2 "Expert
    # Agents — chạy song song"). LangGraph dispatches all three edges from a
    # single superstep concurrently. All three converge at "detect".
    graph.add_edge("plan", "financial")
    graph.add_edge("plan", "policy")
    graph.add_edge("plan", "collateral")
    graph.add_edge("financial", "detect")
    graph.add_edge("policy", "detect")
    graph.add_edge("collateral", "detect")

    # Round limit enforced here, in the edge — not in a system prompt.
    graph.add_conditional_edges("detect", _route_after_detect, {"challenge": "challenge", "done": "synthesize"})
    graph.add_edge("challenge", "detect")
    graph.add_edge("synthesize", "transition")
    graph.add_edge("transition", END)
    return graph


async def build_compiled_graph(checkpointer: AsyncPostgresSaver):
    return _build_uncompiled_graph().compile(checkpointer=checkpointer)


class Checkpointer:
    """Owns the AsyncPostgresSaver's connection pool for the process
    lifetime — opened once in worker/app/main.py's startup, not per job."""

    def __init__(self) -> None:
        self._cm = AsyncPostgresSaver.from_conn_string(_psycopg_dsn(DATABASE_URL))
        self.saver: AsyncPostgresSaver | None = None

    async def __aenter__(self) -> AsyncPostgresSaver:
        # DDL first, via a short-lived ADMIN connection (see module docstring
        # above the ADMIN_DATABASE_URL constant for why this can't reuse the
        # long-lived saver's own — least-privilege — connection).
        async with AsyncPostgresSaver.from_conn_string(_psycopg_dsn(ADMIN_DATABASE_URL)) as admin_saver:
            await admin_saver.setup()  # idempotent — creates checkpoint tables if missing

        # Long-lived saver for actual get/put traffic uses the regular
        # least-privilege connection.
        self.saver = await self._cm.__aenter__()
        return self.saver

    async def __aexit__(self, *exc_info) -> None:
        await self._cm.__aexit__(*exc_info)
