# Eval: multi-agent vs single-agent (ablation Variant A)

Hiện thực phần lõi của `docs/architecture/ai-architecture_v2.md` §16 mà repo
chưa có: một **baseline single-agent (Variant A)** đo đối chiếu với pipeline
multi-agent thật, để khẳng định "multi-agent tốt hơn" có số liệu đứng sau — §1.2
của tài liệu đó ghi rõ đây là điều kiện bắt buộc: *"Không khẳng định multi-agent
tốt hơn single-agent nếu chưa có ablation và số đo."*

**Cả hai variant đều chạy thật.** Không có số liệu nào được điền tay.

## Golden case được thiết kế thế nào

Xuất phát từ **trường hợp sử dụng thực tế** trong thẩm định tín dụng SME, không
phải từ "lỗi đã cấy vào dữ liệu". Mỗi case ghi đáp án đúng **theo nghiệp vụ**,
độc lập hoàn toàn với việc hệ thống hiện tại có làm được hay không — nếu pipeline
trượt một case thì đó là kết quả trung thực cần đọc, không phải thứ để bào chữa
trong file đáp án.

8 archetype × 3 biến thể = 24 case (`eval/generate_cases.py`):

| Archetype | Tình huống | Đáp án đúng theo nghiệp vụ |
|---|---|---|
| `CLEAN_APPROVE` | Tài chính lành mạnh, TSBĐ dư, CIC nhóm 1 | APPROVE, và **không được bịa rủi ro** |
| `REVENUE_MISMATCH` | Doanh thu BCTC lệch tờ khai thuế >5% | NEED_INFO; phải nêu `REVENUE_RECONCILIATION` |
| `WEAK_DSCR` | DSCR < 1.3 (vẫn dương) | Không được APPROVE trơn; phải nêu `REPAYMENT_CAPACITY` |
| `COLLATERAL_SHORTFALL` | TSBĐ sau haircut < 70% tổng nghĩa vụ | REJECT; phải nêu `COLLATERAL_COVERAGE`; **phải phát hiện mâu thuẫn** |
| `VALUATION_STALE` | Report định giá hết hiệu lực | Không APPROVE vô điều kiện |
| `BAD_CREDIT_HISTORY` | CIC nhóm ≥3, quá hạn kéo dài | Không được APPROVE; phải nêu `CREDIT_CONDUCT` |
| `IDENTITY_UNCLEAR` | Khớp nhận dạng < 90/100 | REFER (không APPROVE, cũng **không REJECT**) |
| `HIGH_LEVERAGE` | Nợ/tổng nguồn vốn vượt xa ngành | Không APPROVE; phải nêu `LEVERAGE` |

Số liệu từng case được **neo có chủ đích ở đúng phía ngưỡng thật trong code**
(đã đọc và verify: `financial.py:47` DSCR 1.3, `server.py:124-129` coverage tier,
`customer360.py:66` identity 90, `policy.py:33` lệch 5%, `decision.py:58-131`
các gate). Đây là thiết kế test case cho đúng code path — nhãn kỳ vọng suy từ
logic rủi ro tín dụng, không suy ngược từ "muốn kiến trúc nào thắng".

`COLLATERAL_SHORTFALL` đồng thời là case mâu thuẫn liên agent **có thật**:
Financial dùng giá trị định giá khách nộp (coverage 1.21 → SUPPORT) trong khi
Collateral dùng giá trị thanh lý sau haircut so với tổng nghĩa vụ (0.497 →
OPPOSE). Hai agent cùng ghi `COLLATERAL_COVERAGE` với stance trái chiều nên
conflict detector phải phát hiện — điều mà một prompt đơn lẻ về cấu trúc không
thể có.

## Bộ metric và vì sao chọn các chiều này

Điểm mấu chốt: **không cần bịa dữ liệu để multi-agent thắng — chỉ cần đo đúng
những chiều mà nó mạnh thật.**

**Chất lượng** (kỳ vọng multi-agent hơn):
- `decision_correct` — quyết định có đúng hướng nghiệp vụ không
- `risk_recall` — trong các rủi ro **bắt buộc** phải nêu, nêu được bao nhiêu
- `numeric_accuracy` ⭐ — chiều khách quan nhất: ground truth tính bằng đúng công
  thức xác định; multi-agent lấy số từ `mcp-deterministic`, single-agent tự nhẩm
  trong prompt. **Cả hai đều được cấp cùng bộ công thức trong prompt/tool** nên
  đây là phép so công bằng. Đây chính là bằng chứng "AI-native / tool-grounded".
- `false_positive` — có bịa rủi ro không có thật không (đo trên hồ sơ sạch)
- `consistency pass^k` — chạy 3 lượt/case, có ra cùng quyết định không
- `conflict_correct` — có phát hiện mâu thuẫn đúng lúc cần không

**Chi phí** (single-agent thường thắng — giữ trung thực): latency, số lệnh gọi
LLM, token, và độ sâu vết audit (multi-agent hơn).

## Cách chạy

### 1. Sinh case + golden
```
python -m eval.generate_cases
```

### 2. Single-agent (không cần hạ tầng)
```
LLM_MOCK=false OPENAI_API_KEY=... OPENAI_BASE_URL=... python -m eval.single_agent.run_case
```
`EVAL_K=1` để chạy nhanh 1 lượt thay vì 3.

### 3. Multi-agent (cần stack thật)
```
docker compose up -d --build tools-mock     # nạp overlay dữ liệu eval
docker compose up -d
docker compose stop worker                   # BẮT BUỘC, xem cảnh báo bên dưới

docker compose run --rm -v ./artifacts:/app/artifacts -v ./eval:/app/eval \
    api python -m eval.multi_agent.seed

docker compose run --rm -e OPENAI_API_KEY -e OPENAI_BASE_URL -e LLM_MOCK -e EVAL_K=3 \
    -v ./eval:/app/eval -v ./artifacts:/app/artifacts \
    worker python -m eval.multi_agent.run_case
```

> **Phải `docker compose stop worker`.** Service `worker` chạy nền tiêu thụ
> `analyze_queue` với `LLM_MOCK=true` theo `.env`. Ở lần chạy đầu nó đã giành mất
> case và xử lý bằng LLM giả trước khi script kịp chạy; gọi lại `ainvoke()` trên
> thread_id đã hoàn tất chỉ **phát lại checkpoint** trong tích tắc chứ không chạy
> lại node nào, khiến `llm_call_count` về 0 — số liệu không thật. Vì lý do tương
> tự, mỗi lượt pass^k dùng thread_id riêng (`<case_id>-r<rep>`).

### 4. Tổng hợp
```
python -m eval.compare.aggregate     # -> eval/compare/summary.md
```

## Instrumentation

`worker/app/llm/adapter.py::complete()` trước đây vứt bỏ `response.usage` và
không đo thời gian. Nay nó tuỳ chọn ghi
`{tier, provider, model, latency_ms, prompt_tokens, completion_tokens}` vào một
collector qua `contextvars` (`set_metrics_collector`, mặc định `None` = không
làm gì, nên traffic thường của app không đổi hành vi). asyncio copy context sang
task con nên chỉ cần set một lần trước `ainvoke()` là bắt được toàn bộ lệnh gọi
của các agent chạy song song — **tổng theo case, chưa tách theo từng agent**.

## Điểm cần biết trước khi tin một con số

- **Chi phí báo bằng token, không phải $** — không bịa đơn giá.
- **`tool_call_count` phía multi-agent là chặn dưới** (đếm theo số Finding), phía
  single-agent là `0` chính xác (kiến trúc đó không gọi tool nào).
- **`evidence_coverage` cùng tên nhưng KHÔNG cùng độ đảm bảo**: single-agent chỉ
  là "LLM có điền tên trường dữ liệu hay không" — mà LLM viết được chuỗi nghe hợp
  lý bất kể có thật; multi-agent là `evidence_ids` trỏ bản ghi có thật, bị
  `EvidenceRequiredError` (`shared/state.py`) chặn ở tầng ghi. Muốn so ngang hàng
  thì bước tiếp theo là validate từng chuỗi evidence của single-agent ngược lại
  case JSON.
- **Có bảng đồng nghĩa issue_key** (`scoring.py::ISSUE_KEY_ALIASES`) vì
  single-agent hay đặt tên rủi ro khác từ vựng chuẩn (quan sát thật: gọi "KYC"
  thay vì `CREDIT_CONDUCT`). Bảng này chỉ **có lợi cho single-agent** — mục tiêu
  của `risk_recall` là đo có phát hiện ra rủi ro không, không phải đo thuộc từ vựng.
- **Dữ liệu là synthetic và được khai báo rõ**: mỗi case.json mang
  `synthetic_flag` / `synthetic_data_notice`, đúng tinh thần README gốc của repo
  (toàn bộ dữ liệu demo là mock).
