# SHBExpert Flow — Luồng dữ liệu và hoạt động

> **Bộ tài liệu kiến trúc** — 3 file:
> 1. [`overview.md`](./overview.md) — topology 1-VM, service, ai gọi ai, nguyên tắc an toàn.
> 2. [`ai-architecture.md`](./ai-architecture.md) — bộ não AI: Orchestrator-Workers, agent, tool, RAG, phản biện.
> 3. **`data-flow.md`** (file này) — dữ liệu chảy thế nào qua từng bước, kèm sequence/state diagram.
>
> Nguồn nghiệp vụ: `PRD1.1.docx` mục 4, 7, 9, 10.3, 14 và Phụ lục A.

> **Lưu ý quản trị:** mọi chính sách, ngưỡng và luồng phê duyệt là mô phỏng cho cuộc thi. Hệ thống tạo **khuyến nghị** cho Credit Officer; không phê duyệt, không ký, không giải ngân.

Tên service trong tài liệu này (`web`, `api`, `worker`, `tools-mock`, `postgres`, `qdrant`, `minio`, `redis`) khớp chính xác với [`overview.md`](./overview.md) và với `docker-compose.yml`.

---

## 1. Bản đồ dữ liệu

CaseState là mặt phẳng dữ liệu chung — vừa là blackboard cho agent, vừa là nguồn sự thật cho UI. Bảy nhóm (PRD 10.3):

| Nhóm | Nội dung | Lưu ở đâu |
|---|---|---|
| `identity` | case_id, customer_id, product, requested_facility, owner, state, version | `postgres` |
| `documents` | metadata, extraction, review status, evidence index | `postgres` (metadata + trường bóc tách) · `minio` (file) |
| `tasks` | TaskPlan, dependencies, allowed tools, run status, retries | `postgres` |
| `findings` | Finding có version theo `issue_key` và agent | `postgres` |
| `conflicts` | source findings, questions, rounds, resolution, dissent | `postgres` |
| `decision` | gate results, scores, recommendation, conditions, human action | `postgres` |
| `audit` | immutable event IDs, actor, timestamp, input/output hash, policy/model/tool version | `postgres` (append-only) |

```mermaid
flowchart LR
    subgraph pg["postgres — trạng thái có schema"]
        id["identity"]
        docs["documents<br/><i>metadata + hash + pointer</i>"]
        tasks["tasks"]
        find["findings<br/><i>versioned</i>"]
        conf["conflicts"]
        dec["decision"]
        aud["audit<br/><i>append-only</i>"]
    end

    subgraph mi["minio — object store"]
        files["File gốc theo version<br/>PDF · PNG · XLSX · CSV"]
        memo["Credit memo artifact"]
    end

    subgraph qd["qdrant — tri thức"]
        pol["policy_sme_wc"]
        leg["legal_checklist"]
        indk["industry_knowledge"]
    end

    docs -.->|"document_id + hash<br/>presigned URL"| files
    dec -.-> memo
    find -.->|"policy_citation<br/>policy_id + version"| pol
```

**Ba nguyên tắc lưu trữ:**

- **File không vào state** (PRD 10.1). `postgres` giữ metadata, hash và con trỏ; file gốc nằm ở `minio` theo version. Evidence drawer mở tài liệu bằng presigned URL, không nhồi base64 vào CaseState.
- **Không ghi đè** (FR-02). Tài liệu mới tạo version mới. Hash lưu cùng để chống thay thế âm thầm.
- **Audit chỉ ghi thêm** (FR-12). Bảng event không có quyền `UPDATE`/`DELETE`. Sửa một finding không xoá bản cũ — nó tạo `version: 2` kèm `change_reason`.

---

## 2. State machine hồ sơ

```mermaid
stateDiagram-v2
    [*] --> DRAFT

    DRAFT --> INTAKE_VALIDATION: RM submit intake
    note right of DRAFT
        Owner: RM
        Tạo hồ sơ, khai nhu cầu, tải tài liệu
    end note

    INTAKE_VALIDATION --> NEED_INFO: thiếu tài liệu
    INTAKE_VALIDATION --> ANALYZING: đủ
    note right of INTAKE_VALIDATION
        Owner: Document Pipeline
        Phân loại, bóc tách, đối chiếu checklist
    end note

    NEED_INFO --> INTAKE_VALIDATION: RM bổ sung → revalidate
    note right of NEED_INFO
        Owner: RM
    end note

    ANALYZING --> CHALLENGE: có xung đột
    ANALYZING --> READY_FOR_REVIEW: không xung đột
    note right of ANALYZING
        Owner: Orchestrator + experts
        Chạy tác vụ chuyên môn song song
    end note

    CHALLENGE --> READY_FOR_REVIEW: hợp nhất<br/>(resolved hoặc hết 2 vòng)
    note right of CHALLENGE
        Owner: Orchestrator
        Targeted question, tối đa 2 vòng
    end note

    READY_FOR_REVIEW --> ANALYZING: CO rerun
    READY_FOR_REVIEW --> NEED_INFO: CO return to RM
    READY_FOR_REVIEW --> SUBMITTED_FOR_APPROVAL: CO finalize
    note right of READY_FOR_REVIEW
        Owner: Credit Officer
        Xem, sửa, chạy lại hoặc trả hồ sơ
    end note

    SUBMITTED_FOR_APPROVAL --> CONDITION_FULFILLMENT: outcome từ LOS mock
    note right of SUBMITTED_FOR_APPROVAL
        Owner: Credit Officer
        Khóa version, gửi cấp có thẩm quyền
    end note

    CONDITION_FULFILLMENT --> READY_FOR_DISBURSEMENT: mọi CP đạt
    note right of CONDITION_FULFILLMENT
        Owner: Credit Admin
    end note

    READY_FOR_DISBURSEMENT --> [*]
```

Nguồn: PRD 4.1. Mọi chuyển trạng thái đi qua tool `update_case_status` — tool này **kiểm tra transition có hợp lệ không** trước khi ghi, và sinh audit event. Không có đường tắt: không component nào được `UPDATE cases SET state = ...` trực tiếp.

`READY_FOR_DISBURSEMENT` là điểm dừng của MVP. Giải ngân thật nằm ngoài phạm vi (PRD 3.3).

---

## 3. Luồng end-to-end

Chín bước của PRD 4.2, vẽ ở mức service để nối được với [`overview.md`](./overview.md):

```mermaid
sequenceDiagram
    autonumber
    actor RM
    participant web
    participant api
    participant minio
    participant redis
    participant worker
    participant qdrant
    participant toolsmock as tools-mock
    participant postgres as postgres
    actor CO as Credit Officer

    RM->>web: Tạo case + tải tài liệu
    web->>api: POST /cases · POST /documents
    api->>minio: Lưu file theo version + hash
    api->>postgres: Ghi identity + documents metadata<br/>state = DRAFT
    api-->>web: case_id

    RM->>web: Submit intake
    web->>api: POST /cases/{id}/submit
    api->>postgres: state = INTAKE_VALIDATION
    api->>redis: enqueue job(case_id)
    api-->>web: SSE stream mở

    redis->>worker: dequeue job
    Note over worker: <b>Document Pipeline</b><br/>classify · OCR · extract · checklist
    worker->>minio: Đọc file
    worker->>postgres: ExtractedField + completeness score
    worker->>redis: publish tiến độ
    redis->>api: tiến độ
    api-->>web: SSE → UI cập nhật

    alt Thiếu tài liệu bắt buộc (G1)
        worker->>postgres: state = NEED_INFO
        worker->>api: create_info_request(missing_items, RM)
        Note over worker,api: Dừng — không sinh decision (AS-01)
    else Đủ tài liệu
        Note over worker: <b>Orchestrator</b> lập TaskPlan
        worker->>postgres: tasks + dependency + allowed_tools<br/>state = ANALYZING

        par Expert agents chạy song song
            Note over worker: Financial Agent
            worker->>worker: calculate_ratios (deterministic)
        and
            Note over worker: Policy Agent
            worker->>qdrant: search_policy (filter version trước)
            worker->>toolsmock: get_kyc_result / get_aml_result
        and
            Note over worker: Collateral Agent
            worker->>toolsmock: get_valuation
            worker->>qdrant: search_legal_checklist
        and
            Note over worker: Customer 360 Agent
            worker->>toolsmock: query_cic_mock
        end

        worker->>postgres: Ghi Finding (blackboard)

        Note over worker: <b>Conflict Detector</b><br/>nhóm theo issue_key

        opt Có xung đột
            worker->>postgres: ConflictRecord + state = CHALLENGE
            Note over worker: Targeted question — tối đa 2 vòng
            worker->>postgres: Finding v2 + change_reason
        end

        Note over worker: <b>Decision Synthesis</b><br/>hard gate → scorecard
        worker->>postgres: DecisionPackage + state = READY_FOR_REVIEW
        worker->>redis: publish hoàn thành
        redis->>api: tiến độ
        api-->>web: SSE → Recommendation tab sẵn sàng
    end

    CO->>web: Xem evidence chain
    web->>api: GET /cases/{id}/decision
    api->>minio: presigned URL cho evidence drawer
    CO->>web: Accept / edit / rerun / override (+ reason)
    web->>api: POST /cases/{id}/decision/action
    api->>postgres: version mới + audit event
```

Điểm đáng chú ý trong sơ đồ: **khối `par`**. Bốn expert agent chạy đồng thời — đó là cách đạt NFR-02 (≤ 120s). Nếu chạy tuần tự, 4 agent × ~25s + intake + synthesis đã vượt ngân sách.

---

## 4. Luồng intake và extraction

```mermaid
flowchart TB
    up["RM tải 8–15 tệp"] --> cls["document_classifier<br/><i>tier FAST</i>"]
    cls --> ext["extract_fields<br/><i>tier FAST + OCR</i>"]
    ext --> conf{"confidence<br/>trường quan trọng"}

    conf -->|"≥ 0.85"| ok["Ghi ExtractedField<br/>value + document_id<br/>+ page + bbox"]
    conf -->|"< 0.85"| rev["Gắn <b>REVIEW_REQUIRED</b><br/>chờ người xác nhận"]

    ok --> cmp["compare_fields<br/><i>đối chiếu chéo tài liệu</i>"]
    rev --> cmp

    cmp --> dc{"Phát hiện<br/>mâu thuẫn?"}
    dc -->|"Có"| conflict["<b>DataConflict</b><br/>vd: doanh thu BCTC ≠ tờ khai thuế"]
    dc -->|"Không"| chk

    conflict --> chk["build_checklist<br/><i>theo product · customer_type · collateral</i>"]
    chk --> score["Completeness score"]
    score --> gate{"Đủ tài liệu<br/>bắt buộc?"}
    gate -->|"Không"| ni["state = <b>NEED_INFO</b><br/>create_info_request → RM"]
    gate -->|"Có"| an["state = <b>ANALYZING</b>"]

    style rev fill:#fff4e6
    style conflict fill:#fff4e6
    style ni fill:#fff4e6
    style an fill:#e6f7e6
```

**Mỗi trường bóc tách mang theo nguồn của nó** (FR-03): `value`, `confidence`, `document_id`, `page`, `bbox`. Đây là thứ khiến evidence drawer mở đúng chỗ trên tài liệu cạnh claim, thay vì bắt Credit Officer tự đi tìm. Không có `page`/`bbox` thì evidence chain đứt ở mắt xích cuối và NFR-01 không đạt.

**Checklist là động** (FR-04): sinh theo loại khách hàng, sản phẩm và TSBĐ; hiển thị bốn trạng thái — đủ / thiếu / **hết hạn** / mâu thuẫn — kèm lý do cần. "Hết hạn" là trạng thái riêng vì chứng thư định giá quá hạn là một tình huống thật (flagship case C06).

**OCR lỗi** → document `FAILED`, retry một lần, cho nhập/xác nhận thủ công (PRD 7.1). Không im lặng bỏ qua tài liệu.

---

## 5. Luồng phản biện

Ví dụ thật từ PRD Phụ lục A.2 — conflict `COLLATERAL_COVERAGE` của case C06:

```mermaid
sequenceDiagram
    autonumber
    participant fin as Financial Agent
    participant bb as Blackboard<br/>(CaseState.findings)
    participant orch as Orchestrator
    participant col as Collateral Agent
    participant tools as Deterministic<br/>functions

    fin->>bb: F-FIN-008-v1<br/>issue_key: COLLATERAL_COVERAGE<br/>stance: SUPPORT · conf 0.88
    col->>bb: F-COL-004-v1<br/>issue_key: COLLATERAL_COVERAGE<br/>stance: CAUTION · conf 0.91

    bb->>orch: đọc bảng chung
    Note over orch: Nhóm theo issue_key<br/>SUPPORT vs CAUTION → conflict

    orch->>bb: CF-012 · round 1 · status OPEN

    Note over orch: Chọn agent sở hữu bằng chứng gốc<br/><b>không broadcast</b>

    orch->>col: targeted question<br/>"Coverage sau haircut còn bao nhiêu nếu<br/>loại khoản phải thu quá hạn?"<br/>required_evidence: [AR_AGING, HAIRCUT_RULE]

    col->>tools: calculate_coverage(loại AR quá hạn)
    tools-->>col: coverage = 1.08 · formula_version

    col->>bb: F-COL-004-<b>v2</b><br/>stance: CAUTION (giữ)<br/>change_reason: "Coverage 1.08 sau khi loại AR quá hạn"<br/><i>v1 KHÔNG bị xoá</i>

    bb->>orch: đọc lại
    Note over orch: Còn conflict?

    alt Resolved
        orch->>bb: CF-012 status = RESOLVED
    else round == 2 và vẫn conflict
        orch->>bb: CF-012 status = UNRESOLVED<br/>cả hai finding → dissent[]
        Note over orch: <b>Dừng.</b> Không chọn bên.<br/>Credit Officer xử lý.
    end
```

Ba chi tiết định hình cơ chế này:

- **`round` là biến đếm trong graph**, không phải chỉ dẫn trong prompt. Cạnh `Challenge → Detect` tăng nó; đến 2 là cạnh đóng. Không có cách nào agent "thuyết phục" hệ thống cho thêm vòng.
- **Câu hỏi có `required_evidence`.** Nó không hỏi "bạn nghĩ sao?" mà yêu cầu tính lại với dữ liệu cụ thể và trả về bằng chứng cụ thể.
- **v1 vẫn còn.** Credit Officer xem được agent đã đổi ý thế nào và vì sao — đó là dữ liệu để đánh giá chất lượng agent, không phải rác.

---

## 6. Luồng bổ sung hồ sơ và impact map

Khi RM tải tài liệu mới, hệ thống **không chạy lại mọi agent**. Nó tính bản đồ ảnh hưởng (PRD 4.3):

```mermaid
flowchart LR
    doc["RM tải chứng thư<br/>định giá mới"] --> fields["<b>Trường nào thay đổi?</b><br/>valuation_amount<br/>valuation_date"]
    fields --> findings["<b>Finding nào phụ thuộc?</b><br/>F-COL-004 (coverage)<br/>F-COL-007 (định giá hết hạn)"]
    findings --> agents["<b>Agent nào chạy lại?</b><br/>Document Pipeline<br/>Collateral &amp; Legal<br/>Decision Synthesis"]
    agents --> keep["<b>Agent nào GIỮ NGUYÊN?</b><br/>Financial ✓<br/>Policy ✓<br/>Customer 360 ✓"]
    keep --> ver["<b>DecisionPackage v3</b><br/>version tăng<br/>What changed hiển thị diff"]

    style keep fill:#e6f7e6
    style ver fill:#e6f7e6
```

**Vì sao quan trọng, không chỉ là tối ưu tốc độ:** chạy lại Financial Agent khi không có dữ liệu tài chính nào đổi sẽ tạo ra một finding version mới không lý do — làm nhiễu audit trail và khiến Credit Officer phải đọc lại thứ không đổi. Impact map giữ cho "What changed?" thật sự chỉ hiển thị cái đã thay đổi.

Kỹ thuật: dependency giữa `ExtractedField` → `Finding` → `DecisionPackage` được ghi khi tạo (mỗi Finding đã có `evidence_ids` trỏ tới trường nguồn), nên impact map là **truy vấn đồ thị trên dữ liệu sẵn có**, không phải suy đoán của LLM.

Đây là **AS-04**: *Given RM tải chứng thư mới; When revalidate; Then chỉ task bị ảnh hưởng chạy lại và What changed hiển thị decision version mới.*

---

## 7. Luồng quyết định

```mermaid
flowchart TB
    start["Findings đã resolve<br/>+ dissent (nếu có)"] --> pre{"Mọi hard gate<br/>đã có trạng thái?"}
    pre -->|"Không"| block["<b>Không sinh DecisionPackage</b><br/>guardrail Decision Synthesis"]

    pre -->|"Có"| gates["<b>Bước A — Hard gates</b><br/>G1 → G2 → … → G9"]

    gates -->|"G1 thiếu chứng từ"| ni["<b>NEED_INFO</b>"]
    gates -->|"G2 nhận dạng chưa rõ"| ref1["<b>REFER</b>"]
    gates -->|"G3 mục đích bị cấm"| rej1["<b>REJECT</b> + citation"]
    gates -->|"G4 lệch doanh thu"| ref2["<b>NEED_INFO</b>"]
    gates -->|"G5 TSBĐ không đủ ĐK"| rej2["<b>REJECT</b>"]
    gates -->|"G6 thiếu checklist"| ni
    gates -->|"G7 nợ CIC nhóm ≥3"| rej2
    gates -->|"G8 DSCR < 1.3"| ref1
    gates -->|"G9 định giá hết hiệu lực"| ni

    gates -->|"tất cả PASS"| score["<b>Bước B — Scorecard</b><br/>6 nhóm · tổng 100"]

    score --> th{"Tổng điểm"}
    th -->|"≥ 80"| ap["<b>APPROVE</b>"]
    th -->|"65–79"| apc["<b>APPROVE_WITH_CONDITIONS</b>"]
    th -->|"50–64"| ref3["<b>REFER</b>"]
    th -->|"< 50"| rej3["<b>REJECT</b>"]

    ap --> pkg["<b>DecisionPackage</b><br/>recommendation · amount/tenor<br/>strengths · risks · conditions<br/>dissent · unresolved_questions<br/>policy_version · matrix_version"]
    apc --> cond["compile_conditions<br/>CP · CS · covenants"] --> pkg
    ref3 --> pkg
    rej3 --> pkg

    pkg --> val["validate_evidence_chain<br/><i>mọi claim trọng yếu có evidence_id?</i>"]
    val -->|"Fail"| block2["<b>Chặn</b> — không ghi<br/>NFR-01"]
    val -->|"Pass"| ready["state = <b>READY_FOR_REVIEW</b>"]

    style block fill:#ffe6e6
    style block2 fill:#ffe6e6
    style ready fill:#e6f7e6
```

**Hai chốt chặn ở hai đầu.** Trước khi chấm: hard gate chưa có trạng thái thì không chạy. Sau khi có gói: `validate_evidence_chain` không qua thì không ghi. Một DecisionPackage tồn tại nghĩa là cả hai đã qua.

Chi tiết gate và trọng số scorecard: xem [`ai-architecture.md` §10](./ai-architecture.md#10-logic-quyết-định).

---

## 8. Luồng human-in-the-loop

```mermaid
sequenceDiagram
    autonumber
    actor CO as Credit Officer
    participant web
    participant api
    participant postgres
    participant redis
    participant worker

    CO->>web: Mở Recommendation tab
    web->>api: GET /cases/{id}/decision
    api->>postgres: đọc DecisionPackage + findings + dissent
    api-->>web: gói + evidence links (presigned URL)

    Note over CO,web: Evidence drawer mở đúng trang/vùng<br/>cạnh claim — CO không rời ngữ cảnh

    alt Accept
        CO->>web: Accept
        web->>api: POST /decision/action {accept}
        api->>postgres: version++ · audit event
    else Edit
        CO->>web: Sửa điều kiện + <b>reason bắt buộc</b>
        web->>api: POST /decision/action {edit, reason}
        api->>postgres: version++ · audit event<br/>bản cũ vẫn xem được
    else Rerun
        CO->>web: Yêu cầu chạy lại phần bị ảnh hưởng
        web->>api: POST /decision/action {rerun, scope}
        api->>redis: enqueue job (impact map)
        redis->>worker: chỉ agent liên quan
    else Return to RM
        CO->>web: Trả hồ sơ
        web->>api: POST /decision/action {return, reason}
        api->>postgres: state = NEED_INFO
    else Override
        CO->>web: Ghi đè khuyến nghị
        web-->>CO: ⚠ Cảnh báo nếu trái hard rule<br/>+ ô lý do bắt buộc
        CO->>web: Xác nhận + reason
        web->>api: POST /decision/action {override, reason}
        api->>postgres: version++ · audit event<br/>actor + timestamp + reason
    end

    CO->>web: Khoá version và submit
    web->>api: POST /cases/{id}/submit-for-approval
    api->>postgres: state = SUBMITTED_FOR_APPROVAL
```

**Bốn ràng buộc bất di bất dịch** (FR-11, AS-05):

1. Edit và override **bắt buộc reason** — không có ô trống thì không submit được.
2. Mọi hành động **tăng version**; bản cũ vẫn xem được.
3. Override trái hard rule **hiện cảnh báo trước** khi cho xác nhận.
4. Actor + timestamp + reason vào audit event, không thể sửa sau.

Đây là biện pháp giảm thiểu R7 (automation bias): PRD 12.3 nói rõ **tỷ lệ CO accept cao không phải mục tiêu**. Ma sát ở bước override là có chủ đích — nó buộc người dùng dừng lại và diễn đạt lý do, thay vì bấm qua theo quán tính.

---

## 9. Luồng điều kiện sau phê duyệt

```mermaid
flowchart TB
    los["LOS mock trả outcome<br/><b>APPROVED_WITH_CONDITIONS</b>"] --> orch["Orchestrator<br/>create_condition_tasks"]
    orch --> tasks["Mỗi condition → 1 task<br/>owner · due_date<br/>required_evidence · pass/fail"]
    tasks --> state["state = <b>CONDITION_FULFILLMENT</b>"]
    state --> admin["Credit Admin mở Conditions tab"]

    admin --> attach["Đính kèm chứng từ"]
    attach --> check{"Mọi <b>CP</b><br/>(điều kiện trước giải ngân)<br/>đã đạt?"}
    check -->|"Chưa"| blocked["<b>Chặn</b> — không cho READY<br/>hiển thị CP còn thiếu"]
    check -->|"Rồi"| ready["state = <b>READY_FOR_DISBURSEMENT</b>"]

    blocked --> attach

    style blocked fill:#fff4e6
    style ready fill:#e6f7e6
```

Điều kiện được phân loại: **conditions precedent** (trước giải ngân) · **conditions subsequent** (sau giải ngân) · **covenants** (cam kết). Chỉ CP mới chặn `READY_FOR_DISBURSEMENT`.

Credit Admin **không sửa được kết luận thẩm định** — chỉ đính kèm chứng từ và đánh dấu đạt/chưa đạt (PRD mục 2, Phụ lục B). `create_condition_tasks` là tool có side effect và **chỉ chạy sau approval mock**.

Đây là **AS-06**: *Given outcome APPROVED_WITH_CONDITIONS từ LOS mock; When Credit Admin mở case; Then mọi condition có task, owner, evidence requirement và pass/fail.*

---

## 10. Luồng audit và event

Mỗi bước có ý nghĩa đều phát một event. Audit trail không phải log — nó là **cấu trúc dữ liệu chính** mà Audit tab đọc thẳng.

```mermaid
flowchart LR
    subgraph sources["Nguồn phát event"]
        a1["Hành động người dùng<br/>RM · CO · Admin"]
        a2["Agent run<br/>start · finish · error"]
        a3["Tool call<br/>input · output · latency"]
        a4["State transition"]
        a5["Version bump<br/>finding · decision · document"]
    end

    sources --> ev[("<b>event log</b><br/>append-only<br/>không UPDATE · không DELETE")]

    ev --> tab["Audit tab<br/>timeline bất biến"]
    ev --> replay["Replay<br/>dựng lại run đã lưu"]
    ev --> eval["Evaluation harness<br/>so với gold action trace"]
```

### Event schema

```json
{
  "event_id": "EVT-C06-000142",
  "case_id": "C06",
  "seq": 142,
  "event_type": "TOOL_CALL",
  "actor": { "type": "AGENT", "id": "collateral_legal" },
  "timestamp": "2026-07-17T09:14:22.318Z",
  "payload": {
    "tool": "calculate_coverage",
    "input_hash": "sha256:3f2a…",
    "output_hash": "sha256:9c71…",
    "latency_ms": 34,
    "status": "SUCCESS",
    "error": null
  },
  "versions": {
    "policy_version": "SME-WC-2026.2-MOCK",
    "formula_version": "FIN-0.3-MOCK",
    "model_tier": "reasoning",
    "tool_version": "1.0.0"
  }
}
```

Bốn thứ khiến schema này đủ dùng thay vì chỉ đẹp:

- **`input_hash` / `output_hash`** thay vì nguyên văn — audit chứng minh được "cái gì vào, cái gì ra" mà không đổ PII vào log (NFR-06). Nguyên văn nằm trong CaseState có phân quyền.
- **`versions`** đi kèm mọi event — không có nó thì replay vô nghĩa (NFR-04): cùng input mà policy đổi thì kết quả khác, và không ai biết vì sao.
- **`seq`** đơn điệu theo case — timeline dựng lại được đúng thứ tự kể cả khi các agent chạy song song và timestamp gần nhau.
- **`actor.type`** phân biệt `USER` / `AGENT` / `SYSTEM` — PRD 8.4 yêu cầu tách bạch dữ kiện, suy luận của agent và sửa đổi của người.

Audit tab hiển thị: thứ tự agent/tool, input hash, output hash, latency, trạng thái, error, policy version và người thao tác (FR-12). Nó đọc `postgres`, không đọc `docker logs` — đó là lý do nó trình được cho ban giám khảo.

---

## 11. Đối chiếu luồng ↔ kịch bản demo C06

Flagship case: **An Phú Packaging** — đề nghị hạn mức vốn lưu động 8 tỷ / 12 tháng. Dòng tiền trả nợ chấp nhận được, nhưng doanh thu giữa BCTC và tờ khai thuế **lệch 11%**, chứng thư định giá **sắp hết hạn**, và **42% doanh thu phụ thuộc một người mua**.

Bảng dưới nối 6 mốc của run-of-show 7 phút (PRD 14.2) với mục luồng tương ứng — để người dựng demo biết code phần nào phục vụ phút nào:

| Thời gian | Nội dung demo | Mục luồng | Bằng chứng trên màn hình |
|---|---|---|---|
| 0:00–0:45 | Nêu pain point, mở Case Queue chọn C06 | §2 state machine | Trạng thái, SLA, conflict count |
| 0:45–1:45 | Intake — bóc tách, lộ 11% chênh doanh thu và chứng thư sắp hết hạn | **§4** intake & extraction | Evidence links, checklist 4 trạng thái, `DataConflict` |
| 1:45–2:45 | Planner + tools — 3 agent gọi 3 tool khác nhau | **§3** end-to-end (khối `par`) | Task trace, tool call log có kết quả |
| 2:45–4:00 | Collaboration — Financial SUPPORT / Collateral CAUTION / Policy NEED_DATA | **§5** phản biện | Conflict tab: targeted question + finding v2 |
| 4:00–5:00 | Hành động — `create_info_request`; RM bổ sung; chỉ Intake/Policy/Collateral/Decision chạy lại | **§6** impact map | "What changed?" + side effect có trạng thái |
| 5:00–6:15 | Khuyến nghị — `APPROVE_WITH_CONDITIONS`, 7 tỷ / 9 tháng | **§7** quyết định | Evidence drawer, điều kiện, dissent |
| 6:15–7:00 | Human control — CO sửa điều kiện + lý do, submit; Admin nhận checklist; mở Audit | **§8** HITL · **§9** conditions · **§10** audit | Timeline bất biến |

**Demo phải chứng minh 5 điều** (PRD 14.3), và mỗi điều neo vào một luồng:

1. Ba agent có chuyên môn và tool **khác nhau** — không phải ba prompt giống nhau → §3
2. Ít nhất một mâu thuẫn dẫn tới câu hỏi phản biện và **thay đổi finding có version** → §5
3. Ít nhất một **side effect**: tạo yêu cầu bổ sung / cập nhật trạng thái / tạo condition task → §6, §9
4. Khuyến nghị có bằng chứng, điều kiện, dissent và hard gate — không phải đoạn văn chung chung → §7
5. Con người kiểm soát và mọi thay đổi có audit → §8, §10

---

## 12. Bảng truy vết luồng ↔ FR ↔ acceptance scenario

| Mục | Luồng | FR liên quan | AS |
|---|---|---|---|
| §1 | Bản đồ dữ liệu | FR-02 (không ghi đè, hash, version) | — |
| §2 | State machine | FR-01 (tạo case), FR-12 (audit) | — |
| §3 | End-to-end | FR-05 (TaskPlan), FR-06 (3 agent lõi), FR-07 (≥3 tool call thật) | — |
| §4 | Intake & extraction | FR-03 (bóc tách có trích dẫn), FR-04 (checklist động), FR-13 (yêu cầu bổ sung cho RM) | **AS-01** |
| §5 | Phản biện | FR-08 (ConflictRecord), FR-09 (targeted question, max 2 vòng) | **AS-03** |
| §6 | Impact map | FR-14 (chạy lại theo ảnh hưởng) | **AS-04** |
| §7 | Quyết định | FR-10 (DecisionPackage sau hard gate), FR-16 (xuất tờ trình) | **AS-02** |
| §8 | Human-in-the-loop | FR-11 (accept/edit/rerun/return/override + reason) | **AS-05** |
| §9 | Điều kiện sau phê duyệt | FR-15 (checklist Credit Admin) | **AS-06** |
| §10 | Audit & event | FR-12 (audit dashboard), FR-17 (feedback loop — P2) | — |

FR-18 (theo dõi sau cấp tín dụng) là P2, ngoài demo.

---

## 13. Đọc tiếp

- Hệ thống chạy ở đâu, service nào gọi service nào: [`overview.md`](./overview.md)
- Agent nào, tool nào, phản biện và quyết định ra sao: [`ai-architecture.md`](./ai-architecture.md)
