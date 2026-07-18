"""Credit Memo — computed view over CaseState (case + findings + decision),
NOT a persisted artifact. ai-architecture.md §5.7 lists `generate_credit_memo`
as a Decision Synthesis tool that hasn't been built yet; this is the
web redesign's MVP version, assembled fresh from source data on every
call. GET, not POST: there is no side effect and nothing to persist —
adding a memo table here would just be a second copy of Finding/Decision
data that could silently drift from the rows it's summarizing, the exact
duplication this system avoids everywhere else (see shared/state.py's
docstring on why writes go through one path).

Field shape ported from dashmint_ai-trang's `CreditMemo{caseId, preparedAt,
recommendation, sections: CreditMemoSection{title, content[]}[]}`.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from shared.db import get_session
from shared.models import Case, DecisionPackage, Finding

router = APIRouter(prefix="/cases", tags=["memo"])

AGENT_LABELS = {
    "financial_analysis": "Financial Analysis Agent",
    "policy_compliance": "Policy & Compliance Agent",
    "collateral_legal": "Collateral & Legal Agent",
    "customer_360": "Customer 360 & Credit History Agent",
}


def _latest_findings(session, case_id: str) -> list[Finding]:
    findings = session.execute(select(Finding).where(Finding.case_id == case_id)).scalars().all()
    latest: dict[str, Finding] = {}
    for f in findings:
        cur = latest.get(f.finding_key)
        if cur is None or f.version > cur.version:
            latest[f.finding_key] = f
    return sorted(latest.values(), key=lambda f: f.created_at)


@router.get("/{case_id}/memo")
def get_credit_memo(case_id: str) -> dict:
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")

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
        if decision is None:
            raise HTTPException(
                status_code=409, detail="Chưa có DecisionPackage — chạy phân tích AI trước khi tạo Credit Memo."
            )

        findings = _latest_findings(session, case_id)
        by_agent: dict[str, list[Finding]] = {}
        for f in findings:
            by_agent.setdefault(f.agent_id, []).append(f)

        gate_summary = ", ".join(f"{g['gate_id']}={g['status']}" for g in decision.hard_gates)

        sections = [
            {
                "title": "Khách hàng & khoản vay",
                "content": [
                    f"Khách hàng: {case.customer_id}",
                    f"Sản phẩm: {case.product}",
                    f"Số tiền đề nghị: {case.requested_facility.get('amount_vnd', '—')} VND",
                    f"Kỳ hạn: {case.requested_facility.get('tenor_months', '—')} tháng",
                ],
            },
            {
                "title": "Kết luận tổng hợp",
                "content": [
                    f"Khuyến nghị: {decision.recommendation}",
                    f"Hạn mức đề xuất: {decision.recommended_amount_vnd if decision.recommended_amount_vnd is not None else '—'} VND",
                    f"Hard gates: {gate_summary or '—'}",
                ],
            },
        ]
        for agent_id, agent_findings in by_agent.items():
            sections.append(
                {
                    "title": AGENT_LABELS.get(agent_id, agent_id),
                    "content": [f"[{f.issue_key}] {f.claim}" for f in agent_findings],
                }
            )
        if decision.conditions_precedent:
            sections.append({"title": "Điều kiện tiên quyết", "content": list(decision.conditions_precedent)})

        return {
            "case_id": case_id,
            "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recommendation": decision.recommendation,
            "sections": sections,
        }
