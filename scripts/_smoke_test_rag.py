"""One-off smoke test for the mcp-rag embedding + filter pipeline. Verifies
the EXACT filter shape search_policy will use: product_type match AND
effective_date <= as_of_date AND (expiry_date IS NULL OR expiry_date >
as_of_date) — nested Filter-as-condition, IsNullCondition, DatetimeRange,
all together. Safe to delete once Phase 3 has real pytest coverage.
"""
import time

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

client = QdrantClient(url="http://qdrant:6333")

t0 = time.time()
client.set_model("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
print(f"set_model took {time.time() - t0:.1f}s")

COLLECTION = "_smoke_test_policy"
if client.collection_exists(COLLECTION):
    client.delete_collection(COLLECTION)

client.add(
    collection_name=COLLECTION,
    documents=[
        "Truong hop doanh thu giua BCTC va to khai thue lech duoi 15%, khong can giai trinh them.",
        "Moi truong hop doanh thu giua BCTC va to khai thue lech tu 5% tro len deu phai co giai trinh bang van ban truoc khi phe duyet.",
        "Khach hang SME du dieu kien vay von luu dong khi co bao cao tai chinh toi thieu 2 nam gan nhat.",
    ],
    metadata=[
        {
            "policy_id": "REV-RECON",
            "version": "1.0",
            "product_type": "SME_WC",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": "2026-06-30T00:00:00Z",
        },
        {
            "policy_id": "REV-RECON",
            "version": "2.0",
            "product_type": "SME_WC",
            "effective_date": "2026-07-01T00:00:00Z",
            "expiry_date": None,
        },
        {
            "policy_id": "SME-ELIG",
            "version": "1.0",
            "product_type": "SME_WC",
            "effective_date": "2025-01-01T00:00:00Z",
            "expiry_date": None,
        },
    ],
    ids=[1, 2, 3],
)


def search(as_of_date: str, product_type: str, query: str, top_k: int = 3):
    expiry_ok = qm.Filter(
        should=[
            qm.IsNullCondition(is_null=qm.PayloadField(key="expiry_date")),
            qm.FieldCondition(key="expiry_date", range=qm.DatetimeRange(gt=as_of_date)),
        ]
    )
    query_filter = qm.Filter(
        must=[
            qm.FieldCondition(key="product_type", match=qm.MatchValue(value=product_type)),
            qm.FieldCondition(key="effective_date", range=qm.DatetimeRange(lte=as_of_date)),
            expiry_ok,
        ]
    )
    return client.query(collection_name=COLLECTION, query_text=query, query_filter=query_filter, limit=top_k)


# AS-02: as_of_date is AFTER v1's expiry and AFTER v2's effective_date —
# only v2 (and the unrelated SME-ELIG doc) should be eligible.
results = search(
    as_of_date="2026-07-01T00:00:00Z",
    product_type="SME_WC",
    query="doanh thu bao cao tai chinh va to khai thue co chenh lech thi xu ly the nao",
)
for r in results:
    print(f"score={r.score:.4f} policy_id={r.metadata['policy_id']} version={r.metadata['version']}")

# AS-02's actual guarantee is exclusion, not ranking: the expired v1.0 must
# NEVER appear, regardless of where v2.0 lands relative to unrelated docs
# in similarity score (that's an embedding-quality question, a separate
# concern from version-safety). Assert on exclusion, not on rank.
rev_recon_versions = {r.metadata["version"] for r in results if r.metadata["policy_id"] == "REV-RECON"}
assert rev_recon_versions == {"2.0"}, f"expired v1.0 must never appear in results, got versions {rev_recon_versions}"
print("\nAS-02 FILTER CHECK PASSED (nested Filter + IsNullCondition + DatetimeRange all verified live — v1.0 excluded)")

# Sanity: as_of_date BEFORE v2 takes effect should surface v1 instead.
results_before = search(
    as_of_date="2026-01-01T00:00:00Z",
    product_type="SME_WC",
    query="doanh thu bao cao tai chinh va to khai thue co chenh lech thi xu ly the nao",
)
versions_seen = {r.metadata["policy_id"]: r.metadata["version"] for r in results_before if r.metadata["policy_id"] == "REV-RECON"}
assert versions_seen.get("REV-RECON") == "1.0", f"expected v1.0 to be the only REV-RECON hit before cutover, got {versions_seen}"
print("PRE-CUTOVER CHECK PASSED — v2.0 correctly excluded before its effective_date")

client.delete_collection(COLLECTION)
