# Báo cáo: Đo lường multi-agent so với single-agent (ablation Variant A)

> Tài liệu này mô tả **cách thiết kế và thực hiện phép đo**, không chỉ kết quả.
> Số liệu kết quả nằm ở `eval/compare/summary.md`; cách chạy lại nằm ở
> `eval/README.md`.
>
> Toàn bộ dữ liệu trong bộ eval là **dữ liệu tổng hợp (synthetic)**, được khai
> báo rõ trong từng case (`synthetic_flag`, `synthetic_data_notice`) — nhất
> quán với tuyên bố ở README gốc của dự án.

---

## 1. Vì sao phải làm phép đo này

`docs/architecture/ai-architecture_v2.md` §1.2 ghi rõ một non-goal:

> *"Không khẳng định multi-agent tốt hơn single-agent nếu chưa có ablation và số đo."*

§16.3 của tài liệu đó còn đặc tả sẵn một thang ablation A–E, trong đó **Variant A
= một Credit Agent duy nhất dùng cùng bộ dữ liệu**. Trước công việc này, thang đó
chưa được hiện thực dòng code nào. Báo cáo này hiện thực phần lõi tối thiểu:
**Variant A (single-agent) so với hệ thống multi-agent hiện tại**.

Câu hỏi nghiên cứu, phát biểu ở dạng có thể bác bỏ được:

> Việc tách thành nhiều agent chuyên trách + orchestrator + tool xác định có
> cải thiện **độ đúng quyết định, độ phủ rủi ro, độ chính xác số học, độ ổn
> định và khả năng phát hiện mâu thuẫn** đủ để bù cho phần **latency và chi phí
> token tăng thêm** hay không?

Tiêu chí go/no-go mượn nguyên văn §16.3: *chỉ giữ kiến trúc tách agent nếu nó
cải thiện các chiều chất lượng sau khi đã tính đến latency/cost.*

---

## 2. Thiết kế phép so sánh

Nguyên tắc: **giữ cố định mọi thứ trừ kiến trúc.**

| Yếu tố | Single-agent (Variant A) | Multi-agent (hệ thống hiện tại) |
|---|---|---|
| Model | Llama-3.3-70B-Instruct (FPT AI Factory) | **giống hệt** |
| Tier / tham số | `reasoning`, cùng `max_tokens` | **giống hệt** |
| Đường gọi LLM | `worker/app/llm/adapter.py::complete()` | **cùng hàm đó** |
| Dữ liệu hồ sơ đầu vào | 24 case.json giống nhau | **cùng 24 case** |
| Công thức nghiệp vụ | nêu trong system prompt | mã hoá trong tool xác định |
| Bộ chấm điểm | `eval/common/scoring.py` | **cùng module, cùng hàm** |
| Golden case | `eval/golden_cases.jsonl` | **cùng file** |
| **Kiến trúc** | 1 prompt, 0 tool, 0 ý kiến thứ hai | Orchestrator → 4 agent song song → Conflict Detector → Decision Synthesis |

Biến độc lập duy nhất là kiến trúc. Nếu dùng model khác nhau ở hai phía thì phép
đo sẽ trở thành "so model" chứ không phải "so kiến trúc".

**Quy mô:** 24 case × 3 lượt lặp × 2 variant = **144 lượt chạy thật**. Không có
số liệu nào được điền tay.

---

## 3. Archetype là gì và vì sao chọn cách tiếp cận này

### 3.1 Định nghĩa

**Archetype = một tình huống thẩm định tín dụng điển hình trong thực tế**, đặc
trưng bởi một tín hiệu rủi ro chi phối quyết định.

Ví dụ `WEAK_DSCR` không phải là "case số 7 bị cấy lỗi MUT-003", mà là *"doanh
nghiệp còn có lãi nhưng dòng tiền EBITDA không đủ đệm an toàn để trả nợ gốc và
lãi"* — một tình huống mà bất kỳ hội đồng tín dụng nào cũng gặp hàng tuần.

### 3.2 Vì sao archetype, không phải "mutation đã cấy"

Phiên bản đầu của bộ eval được thiết kế theo hướng **mutation-driven**: xuất phát
từ "dữ liệu này đã bị cấy lỗi gì" rồi mô tả lỗi đó. Cách này sai về phương pháp
và đã bị loại bỏ, vì hai lý do:

1. **Nó mô tả dữ liệu, không mô tả nghiệp vụ.** Một bộ đề tốt phải trả lời được
   "chuyên viên tín dụng giỏi sẽ kết luận gì?", không phải "chúng ta đã sửa
   trường nào trong file JSON?".
2. **Nó đẻ ra trường `known_gap`** — tức là *tự bào chữa cho hệ thống ngay bên
   trong file đáp án* ("case này hệ thống không bắt được vì gate chưa kiểm tra
   loại giấy tờ đó"). Điều này vô lý: golden case là chuẩn để đo, nó phải độc
   lập hoàn toàn với năng lực hiện tại của hệ thống. Nếu pipeline trượt, đó là
   **kết quả cần báo cáo**, không phải thứ để giấu vào bộ đề.

Trường `known_gap` đã được xoá bỏ hoàn toàn.

### 3.3 Bộ 8 archetype

Mỗi archetype có 3 biến thể (khác quy mô doanh nghiệp, ngành, mức độ nghiêm
trọng) → 24 case.

| # | Archetype | Tình huống nghiệp vụ | Tín hiệu chi phối |
|---|---|---|---|
| 1 | `CLEAN_APPROVE` | Hồ sơ lành mạnh mọi mặt | *(không có — đo cảnh báo giả)* |
| 2 | `REVENUE_MISMATCH` | Doanh thu BCTC lệch tờ khai thuế, chưa giải trình | lệch 12–25% |
| 3 | `WEAK_DSCR` | Đệm trả nợ mỏng, biên lợi nhuận hẹp | DSCR 0.85–1.20 |
| 4 | `COLLATERAL_SHORTFALL` | TSBĐ sau thanh lý + haircut không đủ bao phủ tổng nghĩa vụ | coverage 0.497 |
| 5 | `VALUATION_STALE` | Report định giá nội bộ hết hiệu lực | hết hạn trước ngày thẩm định |
| 6 | `BAD_CREDIT_HISTORY` | Nợ xấu CIC, quá hạn kéo dài | nhóm 3–4 |
| 7 | `IDENTITY_UNCLEAR` | Khớp nhận dạng KYC/CIC thấp | 65–84/100 |
| 8 | `HIGH_LEVERAGE` | Cơ cấu vốn mất cân đối, vốn chủ mỏng | tỷ lệ nợ 0.82+ |

`CLEAN_APPROVE` tồn tại vì một bộ eval chỉ toàn hồ sơ xấu sẽ thưởng cho hệ thống
nào **luôn luôn cảnh báo**. Phải có nhóm đối chứng sạch để đo xu hướng bịa rủi ro.

---

## 4. Dữ liệu được tạo như thế nào

Sinh bởi `eval/generate_cases.py` — **tất định hoàn toàn** (không dùng random,
không gọi LLM để sinh số), nên chạy lại luôn ra đúng bộ dữ liệu cũ.

### 4.1 Nguyên tắc "giải ngược từ ngưỡng"

Đây là phần quan trọng nhất về mặt thiết kế.

Muốn một case `WEAK_DSCR` thực sự đi vào code path cần test, số liệu của nó phải
nằm **đúng phía ngưỡng thật trong code**. Nên trước khi sinh dữ liệu, các ngưỡng
được đọc và đối chiếu trực tiếp từ mã nguồn:

| Ngưỡng | Giá trị | Nguồn |
|---|---|---|
| DSCR → SUPPORT/CAUTION | 1.3 | `worker/app/agents/financial.py:47,300` |
| Coverage tier | ≥1.0 OVER / ≥0.7 ADEQUATE / <0.7 UNDER | `mcp-deterministic/app/server.py:124-129` |
| Khớp nhận dạng → NEED_DATA | 90.0 | `worker/app/agents/customer360.py:66,144` |
| Lệch doanh thu → cần giải trình | 5.0% | `worker/app/agents/policy.py:33,68` |
| Hard gate G1–G6 | — | `worker/app/graph/decision.py:58-131` |

Sau đó **giải ngược ra tham số tài chính** thay vì vặn hệ số theo cảm tính. Ví dụ
với DSCR: vì `EBITDA = doanh thu − giá vốn − chi phí HĐ` (chi phí lãi vay triệt
tiêu) và `nghĩa vụ trả nợ = 0.36 × dư nợ`, ta có

```
dư nợ = EBITDA / (0.36 × DSCR mục tiêu)
```

Tương tự với TSBĐ: `giá trị sau haircut = 0.5525 × định giá chính thức`, nên để
rơi vào `UNDER_SECURED` cần `định giá chính thức < 1.27 × tổng nghĩa vụ`.

**Đây là thiết kế test case cho đúng code path, không phải rig kết quả** — nhãn
kỳ vọng vẫn suy từ logic rủi ro tín dụng (mục 5), không suy ngược từ "muốn kiến
trúc nào thắng".

### 4.2 Lần kiểm tra đầu tiên bắt được 3 lỗi thiết kế

Bộ dữ liệu đầu tiên sinh ra **không dùng được**, và việc kiểm tra lại đã phát
hiện ra:

1. `CLEAN_APPROVE` ra coverage tier `ADEQUATE` (0.75) chứ không phải
   `OVER_SECURED` → hồ sơ "sạch" thực chất vẫn bị cảnh báo TSBĐ, làm hỏng nhóm
   đối chứng.
2. `WEAK_DSCR` ra **DSCR âm** (−0.219) → đó là doanh nghiệp đang lỗ, không phải
   "khả năng trả nợ yếu"; phi thực tế và test sai thứ cần test.
3. `BAD_CREDIT_HISTORY` và `HIGH_LEVERAGE` vô tình rơi vào `UNDER_SECURED` → dính
   hard gate G5 (REJECT vì TSBĐ), làm nhiễu tín hiệu mà archetype muốn đo.

Sau khi chuyển sang cách "giải ngược từ ngưỡng", mỗi archetype **chỉ kích hoạt
đúng tín hiệu của nó**.

### 4.3 Case tiếng Việt, đúng schema hệ thống

Mỗi case.json dùng **cùng schema** với `artifacts/cases/*` sẵn có (customer,
application, legal_documents, financials 3 kỳ, transactions, cic_reports,
kyc_screenings, collateral, relationships), nên nạp được qua đúng đường
`scripts/seed_synthetic_cases.py::_seed_one` mà không cần viết lại logic seed.
Tên doanh nghiệp, địa chỉ, mục đích vay, kịch bản đều bằng tiếng Việt.

Bảng cân đối kế toán của mọi kỳ đều **cân** (`tài sản = nguồn vốn`) — không phải
số ngẫu nhiên ghép lại.

### 4.4 Xử lý ràng buộc hệ thống bên ngoài

`tools-mock` (mô phỏng CIC/định giá/nghĩa vụ tín dụng) hardcode dữ liệu theo
case_id và **trả 404 với ID lạ** — nghĩa là case sinh mới sẽ làm Collateral và
Customer360 agent lỗi. Giải pháp: thêm cơ chế nạp **overlay JSON tuỳ chọn**
(`TOOLS_MOCK_OVERLAY`, bind-mount read-only). Không có file overlay thì
`tools-mock` chạy y hệt như cũ, nên demo/dev không bị ảnh hưởng, và dữ liệu eval
không lẫn vào các case demo cố định trong mã nguồn.

---

## 5. Ground truth được tạo như thế nào

Ground truth gồm **3 lớp độc lập**, đo 3 thứ khác nhau.

### 5.1 Lớp 1 — `expected_decision`: một đáp án duy nhất

Mỗi case có **đúng một** quyết định đúng, suy từ logic rủi ro tín dụng:

| Archetype | Đáp án | Lập luận nghiệp vụ |
|---|---|---|
| `CLEAN_APPROVE` | `APPROVE` | Không tín hiệu rủi ro nào vượt ngưỡng |
| `REVENUE_MISMATCH` | `NEED_INFO` | Chênh lệch trọng yếu chưa giải trình làm lung lay chính số liệu mà toàn bộ phân tích dựa vào → phải làm rõ trước |
| `WEAK_DSCR` | `REFER` | Đệm trả nợ không đủ → cần phán quyết của cấp thẩm quyền, không phê duyệt tự động |
| `COLLATERAL_SHORTFALL` | `REJECT` | Thiếu hụt tới ~50% là điều kiện loại trừ, không phải "điều kiện bổ sung" |
| `VALUATION_STALE` | `NEED_INFO` | Chưa biết giá trị TSBĐ hiện tại thì không thể xác định hạn mức |
| `BAD_CREDIT_HISTORY` | `REJECT` | Nợ nhóm 3+ là nợ xấu theo phân loại NHNN |
| `IDENTITY_UNCLEAR` | `REFER` | Phải xác minh danh tính thủ công. Đặc biệt **không được REJECT** — bản ghi khớp thấp có thể là của người khác |
| `HIGH_LEVERAGE` | `REFER` | Cơ cấu vốn mất cân đối cần phán quyết cấp thẩm quyền |

**Rubric chấm chặt**: khớp chính xác mới tính đúng. Một câu trả lời *thận trọng
quá mức* (ví dụ `APPROVE_WITH_CONDITIONS` cho hồ sơ sạch) vẫn bị tính sai; mức
thận trọng thừa được đo riêng bằng chỉ số cảnh báo giả, để hai khái niệm không
trộn vào nhau.

> **Rubric này không thiên vị multi-agent.** Scorecard hiện tại không có hard
> gate cho nợ CIC nhóm 3+, định giá hết hạn, DSCR yếu hay đòn bẩy cao — nên
> chính pipeline multi-agent cũng **trượt 4/8 archetype**. Ở `BAD_CREDIT_HISTORY`,
> single-agent còn đúng hơn multi-agent (0.556 so với 0).

### 5.2 Lớp 2 — `must_flag_risks` / `must_not_flag_risks`

Đo **độ phủ rủi ro** tách rời khỏi quyết định cuối. Một hệ thống có thể ra đúng
quyết định vì lý do sai; lớp này bắt được điều đó.

- `must_flag_risks`: các `issue_key` bắt buộc phải nêu (vd `WEAK_DSCR` →
  `REPAYMENT_CAPACITY`).
- `must_not_flag_risks`: dùng cho `CLEAN_APPROVE` — liệt kê các tín hiệu **lành
  mạnh khách quan trong chính dữ liệu case đó** (DSCR 6.0; lệch doanh thu 0%;
  CIC nhóm 1, khớp 97; TSBĐ OVER_SECURED; cả 4 nhóm tỷ số đều Tốt/Khá so với
  trung bình ngành). Nêu rủi ro ở bất kỳ mục nào trong đó là **cảnh báo giả**.

### 5.3 Lớp 3 — `ground_truth_numbers`

Các con số được tính **bằng đúng công thức của tool xác định**, từ chính số liệu
của case: `dscr`, `debt_ratio`, `current_ratio`, `coverage_ratio_naive`,
`coverage_ratio_after_haircut`, `revenue_mismatch_pct`, `ebitda_vnd`,
`debt_service_annual_vnd`.

Đây là lớp **khách quan nhất** trong toàn bộ bộ đề: không phụ thuộc khẩu vị rủi
ro của ai cả, chỉ là số học. Sai số cho phép 1% tương đối (để không bắt lỗi làm
tròn khi diễn giải).

---

## 6. Bộ metric: đo gì và vì sao

Luận điểm thiết kế: **không cần dựng dữ liệu thiên lệch để multi-agent thắng —
chỉ cần đo đúng những chiều mà nó mạnh thật.** Một prompt đơn lẻ thực sự tự nhẩm
sai số và bỏ sót rủi ro; kiến trúc neo vào tool xác định thì không.

### 6.1 Nhóm chất lượng

| Chỉ số | Đo cái gì | Cách tính |
|---|---|---|
| `decision_correct` | Độ đúng quyết định cuối | khớp chính xác `expected_decision` |
| `risk_recall` | Độ phủ rủi ro | `|đã nêu ∩ bắt buộc| / |bắt buộc|` |
| `numeric_accuracy` ⭐ | Độ chính xác số học | tỷ lệ con số nêu ra khớp ground truth (sai số 1%) |
| `false_positive` | Xu hướng bịa rủi ro | có nêu `issue_key` thuộc `must_not_flag` không |
| `consistency pass^k` | Độ ổn định | tỷ lệ case mà cả 3 lượt ra cùng quyết định |
| `conflict_correct` | Xử lý bất đồng | có phát hiện mâu thuẫn đúng lúc cần không |
| `evidence_coverage` | Mức độ có dẫn chứng | tỷ lệ claim có trỏ bằng chứng |

**`numeric_accuracy` là chỉ số then chốt.** Nó tách bạch được đúng thứ đang tranh
luận: multi-agent lấy số từ `mcp-deterministic` (Python thuần, có
`formula_version`), single-agent phải tự nhẩm trong đầu. Cả hai được cấp **cùng
bộ công thức**, nên chênh lệch phản ánh đúng giá trị của việc neo vào tool — đây
chính là bằng chứng định lượng cho luận điểm "AI-native / tool-grounded".

`conflict_correct` đo một năng lực mà single-agent **về mặt cấu trúc không thể
có**: không có ý kiến thứ hai thì không có gì để mâu thuẫn với chính mình.

### 6.2 Nhóm chi phí — giữ trung thực

Latency, số lệnh gọi LLM, tổng token, số lệnh gọi tool, độ sâu vết audit. Đây là
những chiều single-agent thường thắng, và chúng được báo cáo **ngang hàng** với
nhóm chất lượng. Một báo cáo chỉ khoe chiều mình thắng thì không phải là eval.

### 6.3 Chi phí báo bằng token, không phải tiền

Không quy đổi ra USD vì chưa có bảng giá thật của FPT AI Factory. Bịa một đơn giá
để có con số "$/hồ sơ" đẹp mắt sẽ là số liệu không có căn cứ.

---

## 7. Phép so sánh có công bằng không?

Phần này liệt kê **cả những gì đã làm để công bằng, lẫn những chỗ vốn không thể
cân bằng** — vì che giấu bất đối xứng mới là điều làm hỏng một bài đo.

### 7.1 Những biện pháp đảm bảo công bằng

1. **Cùng model, cùng tier, cùng đường gọi LLM.** Khác biệt đo được không thể do
   model.
2. **Cấp cùng bộ công thức cho single-agent.** System prompt của nó nêu rõ quy
   ước ngân hàng (EBITDA, nghĩa vụ trả nợ năm, DSCR, tỷ lệ nợ, tỷ lệ thanh toán
   hiện hành, cách tính % lệch doanh thu) — vì đó là thông tin mà phía
   multi-agent vốn được "biết" qua tool. Không nêu thì bài kiểm tra số học sẽ
   bất công.
3. **Cấp cùng bộ từ vựng `issue_key`**, kèm **bảng đồng nghĩa**
   (`scoring.py::ISSUE_KEY_ALIASES`) quy các tên gần nghĩa về khoá chuẩn. Bảng
   này **chỉ có lợi cho single-agent** (multi-agent vốn ghi thẳng khoá chuẩn vào
   DB). Lý do: `risk_recall` phải đo *có phát hiện ra rủi ro không*, không phải
   *có thuộc từ vựng không*. Quan sát thật đã xảy ra: single-agent nhận đúng vấn
   đề nhận dạng nhưng gọi nó là `KYC` thay vì `CREDIT_CONDUCT`.
4. **Cùng một module chấm điểm**, cùng hàm, cùng ngưỡng sai số — không có đường
   chấm riêng cho bên nào.
5. **Golden case cố định trước khi chạy toàn bộ**, suy từ logic tín dụng, và
   được giữ nguyên kể cả khi biết trước nó sẽ làm multi-agent trượt 4/8
   archetype.

### 7.2 Những bất đối xứng còn tồn tại (và bản chất của chúng)

| Bất đối xứng | Bản chất | Đã xử lý thế nào |
|---|---|---|
| **Quyền truy cập dữ liệu** | Ở `COLLATERAL_SHORTFALL`, giá trị định giá chính thức + tổng nghĩa vụ nằm ở registry nội bộ (tools-mock), **không có trong bộ hồ sơ tài liệu**. Nhìn từ dữ liệu khách nộp, TSBĐ vẫn đủ (coverage 1.21). Single-agent recall 0.0 ở đây **không phải vì suy luận kém** mà vì không thấy dữ liệu. | Đây đúng là lợi thế kiến trúc (có quyền gọi tool tra cứu nguồn có thẩm quyền), nhưng được **ghi rõ bản chất** trong `summary.md` thay vì để hiểu lầm thành "LLM dốt" |
| **`evidence_coverage` cùng tên, khác độ đảm bảo** | Single-agent: chỉ là "có điền tên trường dữ liệu hay không" — LLM viết được chuỗi nghe hợp lý bất kể có thật. Multi-agent: `evidence_ids` trỏ bản ghi có thật, bị `EvidenceRequiredError` chặn ở tầng ghi. Cả hai cùng ra 1.0 nhưng **không cùng nghĩa**. | Ghi chú rõ; **không** dùng chỉ số này làm luận điểm thắng thua |
| **`tool_call_count`** | Multi-agent là **ước lượng chặn dưới** (đếm theo số Finding); single-agent là `0` **chính xác tuyệt đối** | Ghi rõ trong nhãn cột |
| **Rubric đơn trị** | Kéo `decision_correct` của single-agent xuống vì nó gần như luôn trả `APPROVE_WITH_CONDITIONS` | Công bố rõ; mức thận trọng thừa được đo riêng bằng cảnh báo giả |

### 7.3 Điều chỉnh sau khi thấy kết quả sớm (công bố đầy đủ)

Một nhãn được tinh chỉnh **sau** khi quan sát smoke test: `must_not_flag` của
`CLEAN_APPROVE` được mở rộng thêm `COLLATERAL_COVERAGE`, `LIQUIDITY`,
`PROFITABILITY`, `LEVERAGE`, `ACTIVITY`. Căn cứ: trong chính dữ liệu case đó, cả
4 nhóm tỷ số đều đạt Tốt/Khá so với trung bình ngành và TSBĐ ở mức
`OVER_SECURED` — nên nêu rủi ro ở các mục này là cảnh báo giả **theo dữ liệu**,
không phải theo kết quả của bên nào. Nhãn áp dụng như nhau cho cả hai variant.

---

## 8. Instrumentation và quy trình chạy

### 8.1 Đo token/latency thật

Trước công việc này, `worker/app/llm/adapter.py::complete()` **vứt bỏ
`response.usage`** và không có bộ đếm thời gian — nghĩa là hệ thống không hề có
dữ liệu chi phí/độ trễ thật ở bất kỳ đâu.

Đã bổ sung một hook tối thiểu: nếu có collector được set qua `contextvars`
(`set_metrics_collector`), mỗi lệnh gọi sẽ ghi lại
`{tier, provider, model, latency_ms, prompt_tokens, completion_tokens}`. Mặc
định là `None` → **không đổi hành vi** ở mọi call site hiện tại của ứng dụng.

Dùng `contextvars` (không phải biến toàn cục) vì LangGraph chạy 4 agent song
song trên cùng event loop; asyncio copy context sang task con nên chỉ cần set
một lần trước `ainvoke()` là bắt được toàn bộ lệnh gọi của các nhánh song song.
Hiện gom **theo case**, chưa tách theo từng agent.

### 8.2 Bẫy đã gặp: phát lại checkpoint

Lần chạy đầu tiên cho ra `llm_call_count = 0` — số liệu vô nghĩa. Nguyên nhân:
service `worker` chạy nền tiêu thụ `analyze_queue` với `LLM_MOCK=true` theo
`.env`, đã **giành mất case và xử lý bằng LLM giả** trước khi script kịp chạy.
Gọi lại `ainvoke()` trên một `thread_id` đã hoàn tất chỉ **phát lại checkpoint**
trong tích tắc chứ không chạy lại node nào.

Hai biện pháp: (a) bắt buộc `docker compose stop worker` trước khi đo; (b) mỗi
lượt pass^k dùng `thread_id` riêng (`<case_id>-r<rep>`) — nếu không, lượt 2 và 3
chỉ là bản sao của lượt 1 và chỉ số ổn định sẽ **luôn đẹp một cách giả tạo**.

### 8.3 Chấm lại lúc tổng hợp

`aggregate.py` **chấm lại `decision_correct` từ golden hiện tại** thay vì tin giá
trị đã lưu lúc chạy. Nhờ vậy việc tinh chỉnh rubric không bắt phải chạy lại
pipeline (~30 phút/lượt). Golden là nguồn sự thật duy nhất tại thời điểm báo cáo.

---

## 9. Kết quả tóm tắt

Chi tiết đầy đủ ở `eval/compare/summary.md`.

| Chỉ số chất lượng | single_agent | multi_agent |
|---|---|---|
| Quyết định đúng | 0.125 | **0.500** |
| Risk recall | 0.651 | **0.984** |
| **Numeric accuracy** | 0.117 | **0.784** |
| Consistency pass³ | 0.708 | **0.958** |
| Tỷ lệ cảnh báo giả (thấp = tốt) | 0.125 | **0** |
| Phát hiện mâu thuẫn | 0.5 | **1.0** |

| Chỉ số chi phí | single_agent | multi_agent |
|---|---|---|
| Thời gian chạy (ms) | **10 930** | 23 428 |
| Số lệnh gọi LLM | **1** | 14.0 |
| Tổng token | **3 049** | 3 590 |
| Độ sâu vết audit (lượt 1) | 5.3 | **19.2** |

**Kết luận theo tiêu chí go/no-go §16.3:** kiến trúc tách agent cải thiện rõ rệt
mọi chiều chất lượng, đổi lại ~2.1× độ trễ và ~14× số lệnh gọi LLM (nhưng chỉ
~1.18× token, do mỗi lệnh gọi nhỏ và tập trung hơn). Với nghiệp vụ thẩm định tín
dụng — nơi một quyết định sai đắt hơn nhiều so với 13 giây chờ — đánh đổi này là
hợp lý.

### 9.1 Những chỗ multi-agent trượt (phát hiện có giá trị nhất)

4/8 archetype multi-agent ra sai quyết định: `BAD_CREDIT_HISTORY`,
`VALUATION_STALE`, `WEAK_DSCR`, `HIGH_LEVERAGE`. Nguyên nhân chung: **scorecard
không có hard gate** cho các tín hiệu này, mà điểm nền all-SUPPORT đã là 88/100
nên một chiều yếu vẫn không kéo được xuống dưới ngưỡng APPROVE (80).

Cụ thể ở `BAD_CREDIT_HISTORY`: khách nợ CIC nhóm 3–4 (nợ xấu theo phân loại
NHNN) vẫn nhận `APPROVE`. **Đây là lỗi nghiêm trọng cần sửa**, và single-agent
còn làm đúng hơn ở archetype này. Đề xuất: bổ sung hard gate cho nợ nhóm ≥3,
định giá hết hiệu lực, và DSCR dưới ngưỡng — cùng nhóm với G1–G6 hiện có.

Nếu bộ eval này được thiết kế để "chứng minh multi-agent thắng", những phát hiện
trên đã không xuất hiện.

---

## 10. Các nguồn sai số đã biết

1. **Lỗi 409 khi lặp:** 50/72 lượt multi-agent báo lỗi, phần lớn là
   `update_case_status 409 Conflict` ở lượt 2–3 — case đã chuyển sang
   `READY_FOR_REVIEW` ở lượt 1. Node transition chạy **sau** khi DecisionPackage
   đã ghi, nên quyết định/finding vẫn hợp lệ (đã kiểm: 100% lượt lỗi 409 vẫn có
   quyết định đầy đủ). Muốn sạch tuyệt đối thì mỗi lượt lặp phải seed case_id
   riêng.
2. **Finding tích luỹ qua các lượt lặp:** chạy lại cùng `case_id` mint
   `finding_key` mới, làm số đếm ở lượt 2–3 bị thổi phồng (38 so với 15.9). Đã
   xử lý bằng cách **chỉ lấy lượt 1** cho các chỉ số đếm; chỉ số chất lượng
   không bị ảnh hưởng vì `issue_key` và giá trị metrics lặp lại y hệt.
3. **Chỉ test một model.** Kết luận có thể khác với model mạnh hơn — một model
   có khả năng số học tốt hơn sẽ thu hẹp khoảng cách `numeric_accuracy`.
4. **`evidence_coverage` chưa kiểm tính có thật** — mới đếm sự hiện diện. Bước
   tiếp theo: đối chiếu từng chuỗi evidence của single-agent ngược lại case JSON.
5. **Chưa tách chi phí theo từng agent** — mới gom theo case.
6. **24 case là cỡ mẫu nhỏ**; mỗi archetype chỉ 3 biến thể nên chênh lệch ở mức
   một archetype đơn lẻ chưa đủ mạnh về thống kê.

---

## 11. Hướng mở rộng

- Bổ sung hard gate cho 3 lỗ hổng ở mục 9.1, rồi **chạy lại chính bộ eval này**
  để kiểm chứng — đây là giá trị thực của việc có harness.
- Hiện thực nốt thang ablation B–E của §16.3 (workcell song song → thêm Citation
  Validator → thêm Conflict Checker → thêm Capability Router) để biết **từng
  thành phần** đóng góp bao nhiêu, chứ không chỉ so hai đầu mút.
- Validate tính có thật của evidence (mục 10.4).
- Mở rộng cỡ mẫu và bổ sung archetype đối kháng (prompt injection trong tài
  liệu, tool timeout) theo danh sách 15 kịch bản ở §16.1.
