# Tài liệu SHBExpert Flow — đọc từ đâu

> **Bản authoritative về kiến trúc là [`architecture/ai-architecture_v2.md`](architecture/ai-architecture_v2.md).**
> `ai-architecture.md` (v1) giữ lại làm tham chiếu lịch sử; `overview.md` và
> `data-flow.md` mô tả topology/luồng dữ liệu và vẫn hữu ích, nhưng chỗ nào mâu
> thuẫn với v2 thì lấy v2 làm chuẩn.

Toàn bộ dữ liệu trong hệ thống là **synthetic**, khai báo rõ ở từng case
(`synthetic_flag`). Hệ thống chỉ tạo **khuyến nghị** cho Credit Officer — không
phê duyệt, không ký, không giải ngân. Mọi checklist/ngưỡng/trọng số là **mô
phỏng cho cuộc thi**, không phải quy trình rủi ro chính thức của SHB.

---

## Đọc theo mục đích

| Bạn muốn biết | Đọc file này | Dòng |
|---|---|---|
| Hệ thống gồm gì, service nào gọi service nào | [`architecture/overview.md`](architecture/overview.md) | 267 |
| Kiến trúc AI: Orchestrator, Expert Workcell, evidence, tool boundary | [`architecture/ai-architecture_v2.md`](architecture/ai-architecture_v2.md) | 1884 |
| Dữ liệu chạy qua hệ thống thế nào, state machine, sơ đồ quyết định | [`architecture/data-flow.md`](architecture/data-flow.md) | 571 |
| **Multi-agent có thật sự hơn single-agent không — số đo** | [`eval-multi-vs-single-agent.md`](eval-multi-vs-single-agent.md) | 463 |
| **An toàn AI: grounding, chống hallucination, prompt injection, audit** | [`ai-safety-grounding.md`](ai-safety-grounding.md) | 134 |
| **NLP tiếng Việt: từ vựng nghiệp vụ, semantic search chính sách** | [`nlp-vietnamese-banking.md`](nlp-vietnamese-banking.md) | 200 |
| Dữ liệu synthetic được sinh ra sao | [`synthetic-data-pipeline-plan.md`](synthetic-data-pipeline-plan.md) | 256 |
| Khoảng cách dữ liệu so với yêu cầu PRD §9 | [`data-prd9-matching-report.md`](data-prd9-matching-report.md) | 183 |

---

## Cái gì ĐÃ CHẠY, cái gì còn là thiết kế

`ai-architecture_v2.md` dùng hệ nhãn **CURRENT / TARGET v2 / MOCK / OPEN** (xem
§0 của file đó). Tóm tắt nhanh để không phải đọc hết 1884 dòng:

### Đã chạy thật (CURRENT)

| Năng lực | Bằng chứng trong code |
|---|---|
| Orchestrator + 4 expert agent chạy song song, có conflict detector và challenge loop | `worker/app/graph/build.py` (LangGraph, checkpoint Postgres) |
| Tool boundary qua MCP thật, 4 server tách biệt, phân quyền tool theo agent | `mcp-deterministic` / `mcp-rag` / `mcp-external` / `mcp-state` |
| Tính toán xác định — LLM không bao giờ tự tính số | `mcp-deterministic/app/server.py`, mỗi kết quả có `formula_version` |
| Hard gate G1–G9 chạy TRƯỚC scorecard | `worker/app/graph/decision.py::_check_hard_gates` |
| Bắt buộc bằng chứng cho finding HIGH/CRITICAL | `shared/state.py::write_finding` → `EvidenceRequiredError` |
| Audit log append-only, thu hồi quyền UPDATE/DELETE ở tầng DB | `api/alembic/versions/0002_revoke_events_mutation.py` |
| **Eval harness single-agent vs multi-agent** — 24 case × 3 lượt × 2 variant = 144 lượt chạy thật | [`../eval/`](../eval/), kết quả ở [`../eval/compare/summary.md`](../eval/compare/summary.md) |
| **Phòng thủ prompt injection** cho nội dung không đáng tin | `worker/app/llm/sanitize.py` |
| Chat Orchestrator (hỏi tiếp theo hồ sơ, streaming) | `worker/app/chat/orchestrator.py` |
| Dashboard: queue, overview, expert council, conflicts, recommendation, audit | `web/app/` (Next.js) |

### Còn là thiết kế (TARGET v2) hoặc còn thiếu

Danh sách đầy đủ ở `ai-architecture_v2.md` §17 và `ai-safety-grounding.md` §6.
Những mục đáng chú ý nhất, **công bố rõ chứ không giấu**:

- **Chưa có RBAC/auth** — `api/app/routers/internal.py` ghi rõ.
- **Gate G2 (KYC) fail-open** khi thiếu finding Customer 360 (`decision.py`).
- **Chưa có gate đòn bẩy** — archetype `HIGH_LEVERAGE` vẫn có thể ra `APPROVE`;
  eval công bố con số này thay vì bỏ qua.
- **Agent thứ 5 (Industry) là placeholder** — điểm `INDUSTRY_GOVERNANCE` cố định.
- **Document Processing / OCR chưa có** — `extracted_fields` do seed script ghi.
- **Chưa có test tự động và CI.**

---

## Số liệu nổi bật (đo thật, không ước lượng)

Từ [`eval-multi-vs-single-agent.md`](eval-multi-vs-single-agent.md) — cùng model
(Llama-3.3-70B qua FPT AI Factory), cùng bộ đề, chỉ khác kiến trúc:

| Chỉ số | single-agent | multi-agent |
|---|---|---|
| Quyết định đúng | 0.125 | **0.875** |
| Độ chính xác số học | 0.117 | **0.801** |
| Độ phủ rủi ro (recall) | 0.651 | **1.000** |
| Độ ổn định (pass³) | 0.708 | **1.000** |
| Cảnh báo giả (thấp = tốt) | 0.125 | **0** |
| Thời gian chạy | **~10.9s** | ~20.9s |

Bộ eval này cũng **phát hiện một lỗi an toàn thật** trong chính hệ thống (khách
nợ CIC nhóm 3–4 vẫn được `APPROVE`), lỗi đó đã được vá bằng hard gate G7–G9 và
kiểm chứng lại bằng số: `decision_correct` 0.500 → 0.875. Chi tiết ở
[`ai-safety-grounding.md`](ai-safety-grounding.md) §4.1.
