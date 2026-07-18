# Kết quả eval: multi-agent vs single-agent (ablation Variant A)

- Bộ case: 24 case × 3 lượt lặp mỗi case
- single_agent: 72 lượt chạy | multi_agent: 72 lượt chạy

## Chất lượng (chiều multi-agent kỳ vọng mạnh hơn)

| Chỉ số | single_agent | multi_agent |
|---|---|---|
| Quyết định đúng (decision_correct) | 0.125 | 0.5 |
| Risk recall (nêu đủ rủi ro bắt buộc) | 0.651 | 0.984 |
| Numeric accuracy (số liệu tính đúng) | 0.117 | 0.784 |
| Evidence coverage (claim có dẫn chứng) | 1.0 | 1.0 |
| Consistency pass^k (mọi lượt cùng KQ) | 0.708 | 0.958 |
| Tỷ lệ có cảnh báo giả (thấp = tốt) | 0.125 | 0 |
| Phát hiện mâu thuẫn đúng kỳ vọng | 0.5 | 1 |

## Chi phí (chiều single-agent thường thắng — giữ trung thực)

| Chỉ số | single_agent | multi_agent |
|---|---|---|
| Thời gian chạy (ms) | 10929.601 | 23428.079 |
| Số lệnh gọi LLM | 1 | 14.028 |
| Tổng token | 3049.236 | 3589.736 |
| Số lệnh gọi tool (chỉ lượt 1; multi là chặn dưới) | 0 | 15.25 |
| Số finding (chỉ lượt 1) | 4.333 | 15.25 |
| Độ sâu vết audit (chỉ lượt 1) | 5.333 | 19.208 |

## Theo từng archetype nghiệp vụ

| Archetype | QĐ đúng (single) | QĐ đúng (multi) | Recall (single) | Recall (multi) |
|---|---|---|---|---|
| BAD_CREDIT_HISTORY | 0.556 | 0 | 1.0 | 1.0 |
| CLEAN_APPROVE | 0.444 | 1 | None | None |
| COLLATERAL_SHORTFALL | 0 | 1 | 0.0 | 1.0 |
| HIGH_LEVERAGE | 0 | 0 | 1.0 | 0.889 |
| IDENTITY_UNCLEAR | 0 | 1 | 1.0 | 1.0 |
| REVENUE_MISMATCH | 0 | 1 | 1.0 | 1.0 |
| VALUATION_STALE | 0 | 0 | 0.0 | 1.0 |
| WEAK_DSCR | 0 | 0 | 0.556 | 1.0 |

## Lỗi trong lúc chạy (công bố đầy đủ)

- single_agent: 0/72 lượt lỗi
- multi_agent: 50/72 lượt lỗi — phần lớn là `update_case_status 409 Conflict` ở lượt lặp 2-3. Đây là **hệ quả của cách đo pass^k**, không phải hệ thống hỏng: case đã chuyển sang READY_FOR_REVIEW ở lượt 1 nên state machine từ chối chuyển tiếp lần nữa. Node transition chạy SAU khi DecisionPackage đã ghi, nên quyết định và finding của các lượt đó vẫn hợp lệ (đã kiểm: 100% lượt lỗi 409 vẫn có quyết định đầy đủ). Muốn sạch hoàn toàn thì mỗi lượt lặp phải seed case_id riêng.

## Ghi chú đọc số

- `numeric_accuracy` là chiều khách quan nhất: ground truth tính bằng đúng công thức xác định, multi-agent lấy số từ mcp-deterministic còn single-agent tự nhẩm trong prompt. Cả hai đều được cung cấp cùng bộ công thức nên đây là phép so công bằng.
- `evidence_coverage` của single-agent chỉ là 'có điền tên trường dữ liệu hay không' — LLM viết được một chuỗi nghe hợp lý bất kể có thật hay không. Phía multi-agent là evidence_ids trỏ tới bản ghi có thật, bị `EvidenceRequiredError` (shared/state.py) chặn ở tầng ghi. Cùng tên chỉ số nhưng KHÔNG cùng độ đảm bảo.
- `tool_call_count` của multi-agent là chặn dưới (đếm theo số Finding), của single-agent là 0 chính xác — kiến trúc đó không gọi tool nào.
- **`COLLATERAL_SHORTFALL`: single-agent recall 0.0 KHÔNG phải vì suy luận kém** mà vì giá trị định giá chính thức của ngân hàng và tổng nghĩa vụ nằm ở registry nội bộ (tools-mock), không có trong bộ hồ sơ tài liệu. Nhìn từ dữ liệu khách nộp thì TSBĐ vẫn đủ (coverage 1.21). Đây đúng là lợi thế kiến trúc của multi-agent (có quyền gọi tool tra cứu nguồn có thẩm quyền), nhưng phải nói rõ bản chất là KHÁC BIỆT QUYỀN TRUY CẬP DỮ LIỆU.
- Rubric quyết định chấm CHẶT theo một đáp án duy nhất: một câu trả lời thận trọng quá mức (vd APPROVE_WITH_CONDITIONS cho hồ sơ sạch) vẫn bị tính sai. Điều này kéo decision_correct của single-agent xuống đáng kể; mức thận trọng thừa được đo riêng bằng chỉ số cảnh báo giả.
- Golden case ghi đáp án đúng theo nghiệp vụ tín dụng, không suy ngược từ hành vi hệ thống hiện tại. Chỗ nào hệ thống trượt thì đó là kết quả thật cần đọc, không phải lỗi của bộ đề — xem 4 archetype multi-agent trượt ở bảng trên.

