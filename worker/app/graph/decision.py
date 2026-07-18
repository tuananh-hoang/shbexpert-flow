"""Decision Synthesis — ai-architecture.md §10 / §5.7.

Hard gates run BEFORE the scorecard and can short-circuit straight to a
recommendation (NEED_INFO/REFER/REJECT) — ai-architecture.md §10: "Gate
chạy trước scorecard, không song song, không sau. Một hồ sơ thiếu nghị
quyết vay không nên có điểm số." This is AS-01's guarantee: a case with
an unresolved material gap must not receive a score, however good its
other numbers look.

Decision Synthesis does NOT coordinate other agents and does NOT call
mcp-state itself — it only writes a DecisionPackage via the normal state
layer (write_decision), same as any expert agent writes a Finding. The
STATE TRANSITION to READY_FOR_REVIEW that follows is a separate step,
performed by the graph's "transition" node via mcp-state (the only
side-effect tool call in this whole pipeline so far) — ai-architecture.md
§5.7: "Agent này tổng hợp nhưng KHÔNG điều phối."
"""
from __future__ import annotations

from sqlalchemy import select

from shared.constants import REQUIRED_DOC_TYPES
from shared.db import get_session
from shared.models import Case, ConflictRecord, Document, Finding
from shared.schemas import DecisionPackageIn, HardGateResult, ScoreEntry
from shared.state import write_decision

DECISION_MATRIX_VERSION = "DM-0.3-MOCK"


def _latest_findings(session, case_id: str) -> list[Finding]:
    findings = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
    latest: dict[str, Finding] = {}
    for f in findings:
        cur = latest.get(f.finding_key)
        if cur is None or f.version > cur.version:
            latest[f.finding_key] = f
    return list(latest.values())


def _policy_version_from_events(session, case_id: str) -> str | None:
    """Policy version was recorded on the FINDING_WRITTEN event's
    `versions` field when Policy Agent wrote its finding (see
    shared/state.write_finding's `versions=` param) — not a Finding column,
    so it's read back from the audit log rather than duplicated storage."""
    from shared.models import Event

    row = session.execute(
        select(Event)
        .where(Event.case_id == case_id, Event.event_type == "FINDING_WRITTEN")
        .where(Event.payload["issue_key"].astext == "REVENUE_RECONCILIATION")
        .order_by(Event.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row.versions.get("policy_version") if row else None


def _check_hard_gates(session, case_id: str, findings: list[Finding]) -> tuple[list[HardGateResult], str | None]:
    """Returns (gate_results, early_recommendation). `early_recommendation`
    is None when every gate passes (proceed to scorecard); otherwise it's
    the recommendation the failing gate dictates directly, and the
    scorecard is never computed (AS-01)."""
    gates: list[HardGateResult] = []

    doc_types = {d.doc_type for d in session.execute(select(Document).where(Document.case_id == case_id)).scalars().all()}
    missing = REQUIRED_DOC_TYPES - doc_types
    g1_pass = not missing
    gates.append(HardGateResult(gate_id="G1", status="PASS" if g1_pass else "FAIL", reason=f"thiếu: {sorted(missing)}" if missing else None))
    if not g1_pass:
        return gates, "NEED_INFO"

    # G2 — KYC/AML: Customer 360 / AML agent isn't built yet (deferred to a
    # later phase) — mock PASS rather than fabricate a check with no data.
    gates.append(HardGateResult(gate_id="G2", status="PASS", reason="KYC/AML agent chưa triển khai — mock PASS"))

    # G3 — prohibited use-of-funds category (mock: none configured).
    gates.append(HardGateResult(gate_id="G3", status="PASS", reason=None))

    # G4 — material financial data conflict left unexplained? This is the
    # real gate that fires for C06: Policy Agent's NEED_DATA finding on the
    # BCTC/tax-filing mismatch has no RM-provided explanation on file.
    unexplained = [f for f in findings if f.issue_key == "REVENUE_RECONCILIATION" and f.stance == "NEED_DATA"]
    g4_pass = not unexplained
    gates.append(
        HardGateResult(
            gate_id="G4",
            status="PASS" if g4_pass else "FAIL",
            reason=unexplained[0].claim if unexplained else None,
        )
    )
    if not g4_pass:
        return gates, "NEED_INFO"

    # G5 — collateral legally ineligible with no alternative? A CAUTION
    # stance (needs revaluation) is a condition, not outright ineligibility.
    # Extended to COLLATERAL_OWNERSHIP: an active encumbrance/dispute
    # (OPPOSE — worker/app/agents/collateral.py::run_ownership_check) is the
    # same tier of problem as under-secured coverage, not a fixable gap.
    ineligible = [
        f
        for f in findings
        if f.issue_key in ("COLLATERAL_COVERAGE", "COLLATERAL_OWNERSHIP") and f.stance == "OPPOSE"
    ]
    g5_pass = not ineligible
    gates.append(HardGateResult(gate_id="G5", status="PASS" if g5_pass else "FAIL", reason=ineligible[0].claim if ineligible else None))
    if not g5_pass:
        return gates, "REJECT"

    # G6 — mandatory legal checklist item(s) missing (collateral.py::
    # run_legal_checklist_check, issue_key COLLATERAL_LEGAL_CHECKLIST).
    # Unlike G5, this is fixable paperwork (complete the checklist), not a
    # fundamental disqualification — NEED_INFO, not REJECT, same tier as G4.
    checklist_gap = [f for f in findings if f.issue_key == "COLLATERAL_LEGAL_CHECKLIST" and f.stance == "OPPOSE"]
    g6_pass = not checklist_gap
    gates.append(HardGateResult(gate_id="G6", status="PASS" if g6_pass else "FAIL", reason=checklist_gap[0].claim if checklist_gap else None))
    if not g6_pass:
        return gates, "NEED_INFO"

    return gates, None


def _score_from_stance(stance: str | None, max_score: float) -> float:
    if stance == "SUPPORT":
        return round(max_score * 0.9, 1)
    if stance == "CAUTION":
        return round(max_score * 0.6, 1)
    if stance in ("NEED_DATA", "OPPOSE"):
        return round(max_score * 0.4, 1)
    return round(max_score * 0.7, 1)  # no finding on this dimension yet — neutral, not fabricated


# The 4 standard financial-statement ratio findings (worker/app/agents/
# financial.py::run_financial_agent) — separate from REPAYMENT_CAPACITY
# (DSCR), which stays its own scorecard dimension below.
_STATEMENT_GROUPS = ("LIQUIDITY", "PROFITABILITY", "LEVERAGE", "ACTIVITY")


def _financial_health_stance(by_issue: dict[str, Finding]) -> str | None:
    """Rolls up the 4 ratio-group findings into ONE stance for the
    FINANCIAL_HEALTH dimension, using the same "count >=3/4 groups
    SUPPORT" rule calculate_statement_ratios uses for its own
    count_tot_kha (mcp-deterministic/app/server.py) — 2/4 reads as
    CAUTION, <2/4 as OPPOSE. Returns None if none of the 4 findings exist
    yet (case seeded before this ratio set existed) so the caller falls
    back to the neutral placeholder instead of fabricating a stance."""
    groups = [by_issue[k] for k in _STATEMENT_GROUPS if k in by_issue]
    if not groups:
        return None
    support_count = sum(1 for f in groups if f.stance == "SUPPORT")
    if support_count >= 3:
        return "SUPPORT"
    if support_count == 2:
        return "CAUTION"
    return "OPPOSE"


def _compute_scorecard(findings: list[Finding]) -> list[ScoreEntry]:
    """Simplified 6-group scorecard (ai-architecture.md §10 Bước B).
    Customer 360 / Industry agents aren't built yet, so CREDIT_HISTORY and
    INDUSTRY_GOVERNANCE default to a neutral score rather than being
    computed from data that doesn't exist — an honest placeholder, not a
    fabricated conclusion."""
    by_issue = {f.issue_key: f for f in findings}
    repayment = by_issue.get("REPAYMENT_CAPACITY")
    collateral = by_issue.get("COLLATERAL_COVERAGE")
    policy = by_issue.get("REVENUE_RECONCILIATION")
    financial_health_stance = _financial_health_stance(by_issue)

    return [
        ScoreEntry(dimension="REPAYMENT_CASHFLOW", score=_score_from_stance(repayment.stance if repayment else None, 25), max=25),
        ScoreEntry(dimension="FINANCIAL_HEALTH", score=_score_from_stance(financial_health_stance, 20), max=20),
        ScoreEntry(dimension="CREDIT_HISTORY", score=round(15 * 0.7, 1), max=15),
        ScoreEntry(dimension="COLLATERAL_LEGAL", score=_score_from_stance(collateral.stance if collateral else None, 15), max=15),
        ScoreEntry(dimension="POLICY_COMPLIANCE", score=_score_from_stance(policy.stance if policy else None, 15), max=15),
        ScoreEntry(dimension="INDUSTRY_GOVERNANCE", score=round(10 * 0.7, 1), max=10),
    ]


def _recommendation_from_score(total: float) -> str:
    if total >= 80:
        return "APPROVE"
    if total >= 65:
        return "APPROVE_WITH_CONDITIONS"
    if total >= 50:
        return "REFER"
    return "REJECT"


class EvidenceChainError(ValueError):
    """NFR-01: every strength/risk/dissent entry must trace back to a
    finding that actually has evidence_ids — a DecisionPackage referencing
    an unfounded claim must not be written."""


def _validate_evidence_chain(findings_by_display_id: dict[str, Finding], finding_ids: list[str]) -> None:
    for fid in finding_ids:
        finding = findings_by_display_id.get(fid)
        if finding is None or not finding.evidence_ids:
            raise EvidenceChainError(f"finding {fid!r} referenced in DecisionPackage has no evidence_ids (NFR-01)")


def synthesize_decision_sync(case_id: str) -> dict:
    with get_session() as session:
        case = session.get(Case, case_id)
        findings = _latest_findings(session, case_id)
        findings_by_display_id = {f.display_id: f for f in findings}

        gates, early_recommendation = _check_hard_gates(session, case_id, findings)

        conflicts = session.execute(select(ConflictRecord).where(ConflictRecord.case_id == case_id)).scalars().all()
        dissent_finding_ids: list[str] = []
        for c in conflicts:
            if c.status == "UNRESOLVED":
                dissent_finding_ids.extend(c.source_findings)

        strengths = [f.display_id for f in findings if f.stance == "SUPPORT" and f.display_id not in dissent_finding_ids]
        risks = [
            f.display_id
            for f in findings
            if f.stance in ("CAUTION", "OPPOSE", "NEED_DATA") and f.display_id not in dissent_finding_ids
        ]

        if early_recommendation:
            recommendation = early_recommendation
            scores: list[ScoreEntry] = []
            conditions: list[str] = []
        else:
            scores = _compute_scorecard(findings)
            total = sum(s.score for s in scores)
            recommendation = _recommendation_from_score(total)
            conditions = (
                ["Yêu cầu định giá lại tài sản bảo đảm trước khi giải ngân"]
                if any(f.issue_key == "COLLATERAL_COVERAGE" and f.stance == "CAUTION" for f in findings)
                else []
            )

        _validate_evidence_chain(findings_by_display_id, strengths + risks + dissent_finding_ids)

        requested_amount = case.requested_facility.get("amount_vnd")
        decision_in = DecisionPackageIn(
            case_id=case_id,
            recommendation=recommendation,
            requested_amount_vnd=requested_amount,
            recommended_amount_vnd=requested_amount if recommendation in ("APPROVE", "APPROVE_WITH_CONDITIONS") else None,
            recommended_tenor_months=case.requested_facility.get("tenor_months"),
            hard_gates=gates,
            scores=scores,
            strengths=strengths,
            risks=risks,
            conditions_precedent=conditions,
            dissent=dissent_finding_ids,
            unresolved_questions=[],
            policy_version=_policy_version_from_events(session, case_id),
            decision_matrix_version=DECISION_MATRIX_VERSION,
        )
        result = write_decision(session, decision_in)
        return result.model_dump(mode="json")
