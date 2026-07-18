"""Seed the RAG knowledge collections (ai-architecture.md §8): policy_sme_wc
and legal_checklist. Run inside mcp-rag (has qdrant-client + fastembed):

    docker compose run --rm mcp-rag python -m scripts.seed_policies

Deliberately includes TWO versions of the same policy (REV-RECON) with
overlapping-but-different effective windows — this is the AS-02 test
fixture: "Given chính sách có hai version; When ngày hồ sơ thuộc version
mới; Then citation và rule evaluation dùng đúng version mới" (verified
live against the real filter logic in scripts/_smoke_test_rag.py before
this script was written).

Idempotent: drops and recreates both collections every run (this is
reference/mock data, not user data — safe to fully replace).
"""
from qdrant_client import QdrantClient

QDRANT_URL = "http://qdrant:6333"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FASTEMBED_CACHE_DIR = "/opt/fastembed_cache"  # must match mcp-rag/Dockerfile's pre-warm path

POLICY_COLLECTION = "policy_sme_wc"
LEGAL_COLLECTION = "legal_checklist"

POLICIES = [
    {
        "text": (
            "Trường hợp doanh thu giữa báo cáo tài chính và tờ khai thuế lệch dưới 15%, "
            "không cần giải trình thêm."
        ),
        "metadata": {
            "policy_id": "REV-RECON",
            "version": "1.0",
            "product_type": "SME_WC",
            "section": "Doi chieu doanh thu",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": "2026-06-30T00:00:00Z",
        },
    },
    {
        "text": (
            "Mọi trường hợp doanh thu giữa báo cáo tài chính và tờ khai thuế lệch từ 5% trở "
            "lên đều phải có giải trình bằng văn bản trước khi phê duyệt."
        ),
        "metadata": {
            "policy_id": "REV-RECON",
            "version": "2.0",
            "product_type": "SME_WC",
            "section": "Doi chieu doanh thu",
            "effective_date": "2026-07-01T00:00:00Z",
            "expiry_date": None,
        },
    },
    {
        "text": (
            "Khách hàng SME đủ điều kiện vay vốn lưu động khi có báo cáo tài chính tối thiểu "
            "2 năm gần nhất và không có nợ xấu nhóm 3 trở lên tại các tổ chức tín dụng."
        ),
        "metadata": {
            "policy_id": "SME-ELIG",
            "version": "1.0",
            "product_type": "SME_WC",
            "section": "Dieu kien SME",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": None,
        },
    },
    {
        "text": (
            "Tài sản bảo đảm phải có chứng thư định giá còn hiệu lực tại thời điểm giải ngân; "
            "nếu chứng thư hết hạn trong vòng 60 ngày kể từ ngày dự kiến giải ngân, phải yêu "
            "cầu định giá lại trước khi giải ngân."
        ),
        "metadata": {
            "policy_id": "COLLATERAL-VALUATION",
            "version": "1.0",
            "product_type": "SME_WC",
            "section": "Dinh gia tai san bao dam",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": None,
        },
    },
    {
        "text": (
            "Mọi khách hàng phải hoàn thành KYC và không có cảnh báo AML chưa xử lý trước khi "
            "giải ngân; trường hợp trùng khớp một phần với danh sách cảnh báo phải chuyển "
            "chuyên viên rà soát thủ công, không được tự động kết luận."
        ),
        "metadata": {
            "policy_id": "KYC-AML",
            "version": "1.0",
            "product_type": "SME_WC",
            "section": "KYC/AML",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": None,
        },
    },
]

LEGAL_CHECKLIST = [
    {
        "text": (
            "Chứng thư định giá tài sản bảo đảm phải còn hiệu lực tối thiểu 60 ngày kể từ "
            "ngày giải ngân dự kiến; nếu không đáp ứng, phải yêu cầu định giá lại trước khi "
            "giải ngân."
        ),
        # checklist_id links this Qdrant hit (semantic text + score) back to
        # the structured legal_checklist_template row of the same id
        # (scripts/seed_collateral_reference.py) — collateral.py joins the
        # two by checklist_id to build checklist_items[]/condition_precedent[].
        "metadata": {"collateral_type": "valuation_certificate", "version": "1.0", "checklist_id": "LC-VALUATION-EXPIRY-60D", "is_mandatory": True},
    },
    {
        "text": (
            "Chứng thư định giá phải do thẩm định viên có chứng chỉ hành nghề hợp lệ ký phát "
            "hành; chứng thư không có chữ ký/chứng chỉ hợp lệ không được sử dụng làm căn cứ "
            "tính coverage."
        ),
        "metadata": {"collateral_type": "valuation_certificate", "version": "1.0", "checklist_id": "LC-VALUATION-APPRAISER-LICENSE", "is_mandatory": True},
    },
    {
        "text": (
            "Bất động sản thế chấp phải có giấy chứng nhận quyền sử dụng đất hợp lệ, không có "
            "tranh chấp, và đã đăng ký giao dịch bảo đảm tại cơ quan có thẩm quyền."
        ),
        "metadata": {"collateral_type": "real_estate", "version": "1.0", "checklist_id": "LC-REAL-ESTATE-TITLE", "is_mandatory": True},
    },
]


def main() -> None:
    client = QdrantClient(url=QDRANT_URL)
    client.set_model(EMBEDDING_MODEL, cache_dir=FASTEMBED_CACHE_DIR)

    for collection, rows in [(POLICY_COLLECTION, POLICIES), (LEGAL_COLLECTION, LEGAL_CHECKLIST)]:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.add(
            collection_name=collection,
            documents=[r["text"] for r in rows],
            metadata=[r["metadata"] for r in rows],
            ids=list(range(1, len(rows) + 1)),
        )
        print(f"seeded collection {collection!r} with {len(rows)} documents")


if __name__ == "__main__":
    main()
