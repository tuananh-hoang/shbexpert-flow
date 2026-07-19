"""Engine chấm điểm SLINK — năm agent, đều tất định.

Port phần ĐỌC của shb_credit_agents/src/acas/lib/agents.ts. Không LLM: mọi
agent ở đây là hàm định lượng thuần, nên chạy lại cùng một merchant luôn ra
đúng một kết quả (PRD 14.4 — demo phải lặp lại được).

Đặt ở shared/ chứ không phải worker/: engine là domain logic THUẦN — chỉ
import statistics và shared.constants, không có gì thuộc về worker. Cùng
tính chất đã khiến shared/routing.py nằm ở đây, và nhờ vậy `api` gọi trực
tiếp được cho đường sốc dòng tiền (container api có shared/ nhưng không có
worker/). Spec lát (c) §6 ban đầu ghi worker/app/slink/; đổi sau khi thấy
api cần dùng chung.

Vẫn tách khỏi worker/app/agents/ (agent luồng đỏ) như chủ ý ban đầu: hai
domain khác nhau, bên kia làm việc trên đơn vay còn ở đây là dòng tiền.

Ngoài phạm vi lát (b): agent Operations thực sự cấp/điều chỉnh/treo hạn mức
qua core-banking — đó là lát (c). Engine này dừng ở KHUYẾN NGHỊ.

Spec: docs/superpowers/specs/2026-07-19-slink-scoring-design.md §6
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# Hạn mức tự động tối đa — cùng ngưỡng phân luồng ở shared/constants.py.
# Engine không được khuyến nghị vượt trần mà chính nó dùng để nhận hồ sơ.
from shared.constants import AUTO_APPROVAL_CEILING_VND

APPROVED = "APPROVED"
REJECTED = "REJECTED"


@dataclass
class AgentDecision:
    agent_id: str
    summary: str
    rationale: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass
class ScoringOutcome:
    status: str
    decisions: list[AgentDecision]
    recommended_limit_vnd: int | None = None
    interest_rate_pct: float | None = None
    reason: str = ""


def _vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# 1. Profile — phân loại ngành, thâm niên
# ---------------------------------------------------------------------------
def run_profile_agent(m: dict) -> AgentDecision:
    tenure = m["slink_tenure_months"]
    return AgentDecision(
        agent_id="profile",
        summary=f"{m['name']} — ngành {m['industry']}, mùa vụ: {m['seasonality']}.",
        rationale=[
            f"Ngành nghề: {m['industry']}, đặc thù mùa vụ: {m['seasonality']}.",
            f"Thâm niên sử dụng SLINK: {tenure} tháng.",
            f"Thành lập năm {m['established_year']}.",
        ],
        metrics={"slink_tenure_months": tenure, "industry": m["industry"]},
    )


# ---------------------------------------------------------------------------
# 2. Cashflow — doanh thu bình quân, tăng trưởng, biến động, ngày im lặng
# ---------------------------------------------------------------------------
def run_cashflow_agent(m: dict) -> AgentDecision:
    points = m["cashflow"]
    inflows = [p["inflow_vnd"] for p in points]

    avg_daily = statistics.fmean(inflows) if inflows else 0.0
    avg_monthly = avg_daily * 30

    # Tăng trưởng MoM: 30 ngày gần nhất so với 30 ngày trước đó.
    half = len(points) // 2
    older = statistics.fmean(inflows[:half]) if half else 0.0
    recent = statistics.fmean(inflows[half:]) if half else 0.0
    mom_growth_pct = ((recent - older) / older * 100) if older > 0 else 0.0

    # Biến động = độ lệch chuẩn / trung bình. Cao nghĩa là dòng tiền thất
    # thường, hạn mức phải thận trọng hơn.
    volatility_pct = (statistics.pstdev(inflows) / avg_daily * 100) if avg_daily > 0 else 0.0

    silent_days = sum(1 for v in inflows if v == 0)

    return AgentDecision(
        agent_id="cashflow",
        summary=f"Doanh thu bình quân {_vnd(avg_monthly)} VND/tháng, biến động {volatility_pct:.0f}%.",
        rationale=[
            f"Dòng tiền vào bình quân {_vnd(avg_daily)} VND/ngày ({_vnd(avg_monthly)} VND/tháng).",
            f"Tăng trưởng chu kỳ gần nhất: {mom_growth_pct:+.1f}%.",
            f"Biến động dòng tiền: {volatility_pct:.0f}%.",
            f"Số ngày không phát sinh giao dịch: {silent_days}/{len(points)}.",
            f"Tỉ lệ giao dịch ban đêm: {m['night_transaction_share_pct']}%.",
        ],
        metrics={
            "avg_monthly_revenue_vnd": round(avg_monthly),
            "mom_growth_pct": round(mom_growth_pct, 1),
            "volatility_pct": round(volatility_pct, 1),
            "silent_days": silent_days,
        },
    )


# ---------------------------------------------------------------------------
# 3. Behavioural — điểm hành vi 0-100
# ---------------------------------------------------------------------------
_COUNTERPARTY_BONUS = {"tin cậy": 10, "trung bình": 0, "cần xác minh": -15}


def run_behavioural_agent(m: dict) -> AgentDecision:
    casa = m["casa_retention_pct"]
    payment = m["payment_history_score"]
    quality = m["counterparty_quality"]
    tenure = m["slink_tenure_months"]

    counterparty_bonus = _COUNTERPARTY_BONUS.get(quality, 0)
    tenure_bonus = 5 if tenure >= 24 else 0

    # Công thức giữ nguyên bản gốc (acas/lib/agents.ts::runBehaviouralAgent).
    score = 0.5 * casa + 0.5 * payment + counterparty_bonus + tenure_bonus
    score = max(0.0, min(100.0, score))

    return AgentDecision(
        agent_id="behavioural",
        summary=f"Điểm hành vi tổng hợp: {score:.1f}/100.",
        rationale=[
            f"Tỉ lệ duy trì số dư CASA: {casa}%.",
            f"Điểm lịch sử thanh toán: {payment}/100.",
            f"Chất lượng đối tác giao dịch: {quality} ({counterparty_bonus:+d} điểm).",
            f"Thâm niên SLINK {tenure} tháng ({tenure_bonus:+d} điểm gắn kết).",
        ],
        metrics={"behavioural_score": round(score, 1)},
    )


# ---------------------------------------------------------------------------
# 4. Sizing & Pricing — hạn mức đề xuất + lãi suất
# ---------------------------------------------------------------------------
def run_sizing_pricing_agent(
    m: dict, avg_monthly_revenue_vnd: float, behavioural_score: float, volatility_pct: float
) -> AgentDecision:
    # Hạn mức nền = 40% doanh thu bình quân tháng. Nhân hệ số theo điểm hành
    # vi, rồi chiết khấu nếu dòng tiền thất thường.
    base = avg_monthly_revenue_vnd * 0.40

    if behavioural_score >= 80:
        behaviour_factor, tier = 1.20, "tốt"
    elif behavioural_score >= 60:
        behaviour_factor, tier = 1.00, "khá"
    elif behavioural_score >= 40:
        behaviour_factor, tier = 0.70, "trung bình"
    else:
        behaviour_factor, tier = 0.40, "yếu"

    volatility_discount = 0.80 if volatility_pct > 35 else 1.00

    limit = base * behaviour_factor * volatility_discount
    # Không bao giờ khuyến nghị vượt trần tự động — vượt trần thì đáng lẽ
    # hồ sơ đã không vào luồng xanh ngay từ bước phân luồng.
    limit = min(limit, AUTO_APPROVAL_CEILING_VND)
    limit = round(limit / 1_000_000) * 1_000_000  # làm tròn tới triệu

    # Lãi suất: nền 12%/năm, thưởng hành vi tốt, phạt biến động cao.
    rate = 12.0
    if behavioural_score >= 80:
        rate -= 1.5
    elif behavioural_score < 40:
        rate += 2.0
    if volatility_pct > 35:
        rate += 1.0

    rationale = [
        f"Hạn mức nền = 40% doanh thu bình quân tháng = {_vnd(base)} VND.",
        f"Hệ số hành vi ({tier}, {behavioural_score:.1f}/100): ×{behaviour_factor:.2f}.",
    ]
    if volatility_discount < 1:
        rationale.append(f"Biến động {volatility_pct:.0f}% > 35% — chiết khấu ×{volatility_discount:.2f}.")
    if limit >= AUTO_APPROVAL_CEILING_VND:
        rationale.append(f"Chạm trần hạn mức tự động {_vnd(AUTO_APPROVAL_CEILING_VND)} VND.")
    rationale.append(f"Lãi suất đề xuất: {rate:.1f}%/năm.")

    return AgentDecision(
        agent_id="sizing_pricing",
        summary=f"Đề xuất hạn mức {_vnd(limit)} VND, lãi suất {rate:.1f}%/năm.",
        rationale=rationale,
        metrics={"recommended_limit_vnd": int(limit), "interest_rate_pct": round(rate, 1)},
    )


# ---------------------------------------------------------------------------
# 5. Risk & Compliance — có quyền CHẶN CỨNG
# ---------------------------------------------------------------------------
def run_risk_compliance_agent(m: dict, silent_days: int, mom_growth_pct: float) -> AgentDecision:
    blocks: list[str] = []
    notes: list[str] = []

    # Giao dịch vòng = dấu hiệu thổi phồng doanh thu để vay được nhiều hơn.
    # Chặn cứng bất kể điểm hành vi bao nhiêu — giống cách agent Document
    # Checklist của luồng đỏ hard-fail khi thấy dấu hiệu giả mạo.
    if m["circular_transaction_flag"]:
        blocks.append("phát hiện dấu hiệu giao dịch vòng giữa các tài khoản liên quan")

    night_share = m["night_transaction_share_pct"]
    if night_share > 60:
        blocks.append(f"tỉ lệ giao dịch ban đêm {night_share}% vượt ngưỡng bất thường 60%")
    elif night_share > 30:
        notes.append(f"tỉ lệ giao dịch ban đêm {night_share}% cao hơn thông thường nhưng chưa tới ngưỡng chặn.")

    if mom_growth_pct <= -30:
        blocks.append(f"doanh thu giảm {abs(mom_growth_pct):.0f}% so với chu kỳ trước")

    if silent_days > 20:
        notes.append(f"{silent_days} ngày không phát sinh giao dịch — hoạt động đứt quãng.")

    if blocks:
        return AgentDecision(
            agent_id="risk_compliance",
            summary="Chặn: " + "; ".join(blocks) + ".",
            rationale=blocks + notes,
            metrics={"blocked": True, "block_count": len(blocks)},
        )

    return AgentDecision(
        agent_id="risk_compliance",
        summary="Không phát hiện dấu hiệu rủi ro chặn cấp hạn mức.",
        rationale=(notes or ["Không có cờ giao dịch vòng, tỉ lệ giao dịch đêm trong ngưỡng."]),
        metrics={"blocked": False, "block_count": 0},
    )


# ---------------------------------------------------------------------------
# Điều phối — chạy tuần tự, trả kết quả cuối
# ---------------------------------------------------------------------------
def score_merchant(m: dict) -> ScoringOutcome:
    """Chạy đủ 5 agent trên một merchant và tổng hợp quyết định.

    Thứ tự có phụ thuộc thật: sizing cần số liệu của cashflow và
    behavioural; risk cần số liệu của cashflow.
    """
    profile = run_profile_agent(m)
    cashflow = run_cashflow_agent(m)
    behavioural = run_behavioural_agent(m)

    sizing = run_sizing_pricing_agent(
        m,
        avg_monthly_revenue_vnd=cashflow.metrics["avg_monthly_revenue_vnd"],
        behavioural_score=behavioural.metrics["behavioural_score"],
        volatility_pct=cashflow.metrics["volatility_pct"],
    )
    risk = run_risk_compliance_agent(
        m,
        silent_days=cashflow.metrics["silent_days"],
        mom_growth_pct=cashflow.metrics["mom_growth_pct"],
    )

    decisions = [profile, cashflow, behavioural, sizing, risk]

    if risk.metrics["blocked"]:
        return ScoringOutcome(
            status=REJECTED,
            decisions=decisions,
            recommended_limit_vnd=None,
            interest_rate_pct=None,
            reason=risk.summary,
        )

    limit = sizing.metrics["recommended_limit_vnd"]
    if limit <= 0:
        return ScoringOutcome(
            status=REJECTED,
            decisions=decisions,
            reason="Dòng tiền không đủ để cấp hạn mức thấu chi có ý nghĩa.",
        )

    return ScoringOutcome(
        status=APPROVED,
        decisions=decisions,
        recommended_limit_vnd=limit,
        interest_rate_pct=sizing.metrics["interest_rate_pct"],
        reason=sizing.summary,
    )
