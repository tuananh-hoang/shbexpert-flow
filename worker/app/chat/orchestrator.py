"""Chat Orchestrator — ai-architecture_v2.md §11.8.

Routes a free-form question to one or more domain responders matching
this app's real 4 expert agents (financial_analysis / policy_compliance /
collateral_legal / customer_360), then either streams that single
responder's answer directly (single-domain question) or runs every
matched responder to completion concurrently and streams a short
synthesis over them (compound question) — the same Orchestrator-Workers
shape as the analysis pipeline (worker/app/graph/build.py: plan -> fan-out
-> synthesize), just at chat turn-around speed (seconds) and with no
LangGraph/Redis/checkpoint: one HTTP request in, one streamed response
out (see worker/app/chat/server.py).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.agents.common import run_sync
from app.chat.context import load_case_snapshot_sync, load_recent_messages_sync
from app.llm.adapter import complete, stream_complete

DOMAIN_LABELS = {
    "financial_analysis": "Financial Analysis Agent",
    "policy_compliance": "Policy & Compliance Agent",
    "collateral_legal": "Collateral & Legal Agent",
    "customer_360": "Customer 360 & Credit History Agent",
}

# Deterministic keyword routing — a plain function, not an LLM call,
# matching the same "deterministic rules first" posture the analysis
# pipeline's conflict detector uses (worker/app/graph/conflict.py). Cheap
# and instant, so it adds no latency before the LLM call actually starts.
_ROUTING_KEYWORDS: dict[str, list[str]] = {
    "financial_analysis": [
        "dscr", "tài chính", "doanh thu", "lợi nhuận", "dòng tiền", "thanh khoản",
        "đòn bẩy", "ebitda", "tỷ số", "coverage", "vòng quay",
    ],
    "policy_compliance": [
        "chính sách", "policy", "quy định", "tuân thủ", "kyc", "aml", "đối chiếu doanh thu",
    ],
    "collateral_legal": [
        "tài sản đảm bảo", "tsbđ", "thế chấp", "định giá", "pháp lý", "sở hữu",
        "haircut", "chứng thư", "coverage ratio",
    ],
    "customer_360": [
        "quan hệ tín dụng", "cic", "dư nợ", "quá hạn", "bên liên quan",
        "nhóm khách hàng", "khách hàng 360", "hạn mức",
    ],
}


def route_domains(message: str) -> list[str]:
    """If nothing matches, fall back to ALL 4 domains rather than
    guessing one — gathering more context than needed is safe; silently
    answering from zero domains is not."""
    lowered = message.lower()
    matched = [agent_id for agent_id, keywords in _ROUTING_KEYWORDS.items() if any(k in lowered for k in keywords)]
    return matched or list(_ROUTING_KEYWORDS.keys())


def _format_domain_findings(findings: list[dict]) -> str:
    if not findings:
        return "(agent này chưa có finding nào cho hồ sơ này)"
    lines = []
    for f in findings:
        metrics_str = ", ".join(f"{k}={v}" for k, v in f["metrics"].items())
        lines.append(f"- [{f['issue_key']}] ({f['stance']}, {f['severity']}) {f['claim']}" + (f" — {metrics_str}" if metrics_str else ""))
    return "\n".join(lines)


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(chưa có tin nhắn trước đó)"
    return "\n".join(f"{'CO' if m['role'] == 'USER' else 'Agent'}: {m['content']}" for m in history)


_SYSTEM_PROMPT_BASE = (
    "Bạn là trợ lý AI trong hệ thống thẩm định tín dụng SHBExpert Flow, đang hỗ trợ Credit Officer "
    "hỏi thêm về một hồ sơ CỤ THỂ. Bạn CHỈ được trả lời dựa trên dữ liệu case được cung cấp trong "
    "phần CONTEXT dưới đây — không dùng kiến thức ngoài, không tự tính lại số liệu, không suy đoán "
    "dữ liệu không có trong context. Nếu context không có thông tin cần thiết, hãy nói rõ là chưa có "
    "dữ liệu, không bịa. Nếu Credit Officer yêu cầu một hành động ghi (tạo yêu cầu bổ sung, gửi RM, "
    "phê duyệt, tính lại chỉ số...), hãy trả lời rằng thao tác đó cần thực hiện trực tiếp trên "
    "dashboard, bạn không có quyền thực thi. Trả lời bằng tiếng Việt, ngắn gọn, tự nhiên như một "
    "đồng nghiệp — có thể trích tên chủ đề trong ngoặc vuông, ví dụ [REPAYMENT_CAPACITY], khi phù hợp "
    "nhưng không bắt buộc mỗi câu phải có trích dẫn."
)


def _build_user_prompt(agent_id: str, snapshot: dict, message: str, history_text: str) -> str:
    findings_text = _format_domain_findings(snapshot["findings_by_agent"].get(agent_id, []))
    return (
        f"CONTEXT — Hồ sơ {snapshot['case_id']} ({snapshot['product']}, trạng thái {snapshot['state']}).\n"
        f"Finding của {DOMAIN_LABELS[agent_id]}:\n{findings_text}\n\n"
        f"Lịch sử hội thoại gần đây:\n{history_text}\n\n"
        f"Câu hỏi của Credit Officer: {message}"
    )


async def _domain_response(agent_id: str, snapshot: dict, message: str, history_text: str) -> str:
    user = _build_user_prompt(agent_id, snapshot, message, history_text)
    return await complete(tier="reasoning", system=_SYSTEM_PROMPT_BASE, user=user)


async def handle_chat_turn(case_id: str, thread_id: str, message: str) -> AsyncIterator[str]:
    snapshot = await run_sync(load_case_snapshot_sync, case_id)
    history = await run_sync(load_recent_messages_sync, thread_id)
    history_text = _format_history(history)

    domains = route_domains(message)

    if len(domains) == 1:
        # Single domain — stream the LLM call directly, real token-by-token
        # output, lowest latency.
        agent_id = domains[0]
        user = _build_user_prompt(agent_id, snapshot, message, history_text)
        async for chunk in stream_complete(tier="reasoning", system=_SYSTEM_PROMPT_BASE, user=user):
            yield chunk
        return

    # Compound question — run every matched domain responder to completion
    # CONCURRENTLY (not streamed individually — corrupting an interleaved
    # multi-source stream would be worse than a short wait), then ONE
    # short synthesis call combines them; that synthesis call is the one
    # actually streamed to the user (ai-architecture_v2.md §11.8 step 4).
    responses = await asyncio.gather(*(_domain_response(a, snapshot, message, history_text) for a in domains))
    combined = "\n\n".join(f"[{DOMAIN_LABELS[a]}]\n{r}" for a, r in zip(domains, responses))
    synthesis_system = (
        _SYSTEM_PROMPT_BASE
        + " Dưới đây là câu trả lời riêng của từng agent chuyên môn cho câu hỏi này — hãy GHÉP thành "
        "một câu trả lời liền mạch, không lặp lại tiêu đề agent, không thêm thông tin ngoài các câu trả lời đó."
    )
    synthesis_user = f"Câu hỏi gốc: {message}\n\nCác câu trả lời chuyên môn:\n{combined}"
    async for chunk in stream_complete(tier="reasoning", system=synthesis_system, user=synthesis_user):
        yield chunk
