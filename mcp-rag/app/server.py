"""mcp-rag — MCP server wrapping Qdrant for policy/legal/industry RAG.

Allowlist (ai-architecture.md §6.1): Policy, Collateral, Industry agents.
Financial Agent has no client configured for this server, so it has no
way to call search_policy even if a malicious document tells it to
(ai-architecture.md §5, R2/R8 mitigation) — enforced by MCP connection
topology, not by prompt discipline.

Embeddings are computed LOCALLY via qdrant-client's fastembed integration
(no external API key, no per-call cost) using a small multilingual ONNX
model — good enough for demo-scale Vietnamese semantic search. Verified
live (scripts/_smoke_test_rag.py) that qdrant-client's curated model list
does NOT include the `intfloat/multilingual-e5-small` name one might guess
first; `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is
the smallest model in the list that's actually multilingual.

Every real tool here filters Qdrant metadata (policy_id/version/
effective_date/expiry_date/product_type) BEFORE ranking — see
ai-architecture.md §8 "Filter trước, search sau". This is enforced by
passing `query_filter` directly to `.query()` (a single native Qdrant
call, filter-then-HNSW-search, not two separate passes) so an
out-of-version clause is excluded from the candidate set entirely — it
can never win on similarity score alone. Verified live: a nested
`Filter` (must/should) combining `IsNullCondition` (expiry_date IS NULL)
with `DatetimeRange` (expiry_date > as_of_date) works correctly inside
the outer `must` list.
"""
# NOTE: deliberately NO `from __future__ import annotations` — see
# mcp-deterministic/app/server.py for why (mcp==1.12.4's FastMCP tool
# registration breaks on PEP 563 stringized annotations for any
# @mcp.tool() function that takes typed parameters).
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

SERVER_NAME = "mcp-rag"
PORT = 8201
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Must match the Dockerfile's build-time pre-warm step exactly, or this
# falls back to fastembed's default cache dir and re-downloads at runtime
# (defeating the whole point of pre-warming — see Dockerfile comment).
FASTEMBED_CACHE_DIR = os.environ.get("FASTEMBED_CACHE_DIR", "/opt/fastembed_cache")

POLICY_COLLECTION = "policy_sme_wc"
LEGAL_COLLECTION = "legal_checklist"

mcp = FastMCP(SERVER_NAME)
qdrant = QdrantClient(url=QDRANT_URL)
# cache_dir matches the Dockerfile's build-time pre-warm exactly, so this
# loads the already-baked-in model from disk instead of hitting HuggingFace.
qdrant.set_model(EMBEDDING_MODEL, cache_dir=FASTEMBED_CACHE_DIR)


@mcp.tool()
def ping() -> dict:
    """Health-check tool — not part of the real tool allowlist."""
    return {"status": "ok", "server": SERVER_NAME, "qdrant_url": QDRANT_URL}


def _expiry_ok_filter(as_of_date: str) -> qm.Filter:
    """expiry_date IS NULL OR expiry_date > as_of_date — the OR needs a
    nested Filter(should=...) used as a single condition inside the outer
    Filter(must=...); verified this composes correctly (see module docstring)."""
    return qm.Filter(
        should=[
            qm.IsNullCondition(is_null=qm.PayloadField(key="expiry_date")),
            qm.FieldCondition(key="expiry_date", range=qm.DatetimeRange(gt=as_of_date)),
        ]
    )


@mcp.tool()
def search_policy(query: str, product_type: str, as_of_date: str, top_k: int = 3) -> dict:
    """Semantic search over the policy_sme_wc collection, restricted to
    clauses in effect at `as_of_date` for `product_type` BEFORE ranking.
    Returns citation-bearing hits (policy_id, version, section, effective
    date) so the caller can build a PolicyFinding with a full citation
    (ai-architecture.md §5.3: policy_id + version + effective_date +
    section + source text, or the finding must not be written)."""
    query_filter = qm.Filter(
        must=[
            qm.FieldCondition(key="product_type", match=qm.MatchValue(value=product_type)),
            qm.FieldCondition(key="effective_date", range=qm.DatetimeRange(lte=as_of_date)),
            _expiry_ok_filter(as_of_date),
        ]
    )
    hits = qdrant.query(collection_name=POLICY_COLLECTION, query_text=query, query_filter=query_filter, limit=top_k)
    return {
        "results": [
            {
                "policy_id": h.metadata["policy_id"],
                "version": h.metadata["version"],
                "section": h.metadata.get("section"),
                "effective_date": h.metadata["effective_date"],
                "text": h.document,
                "score": h.score,
            }
            for h in hits
        ]
    }


@mcp.tool()
def search_legal_checklist(collateral_type: str, query: str, top_k: int = 3) -> dict:
    """Semantic search over legal_checklist, restricted to the collateral
    type being assessed — Collateral & Legal Agent's allowlist tool.
    `checklist_id`/`is_mandatory` are passed through from the Qdrant
    payload (scripts/seed_policies.py) so collateral.py can join this
    semantic hit back to the structured legal_checklist_template/
    regulatory_reference/checklist_completion rows (Postgres) by id —
    without these two fields the caller has no way to match a citation to
    its structured status, and would treat every item as unmatched."""
    query_filter = qm.Filter(must=[qm.FieldCondition(key="collateral_type", match=qm.MatchValue(value=collateral_type))])
    hits = qdrant.query(collection_name=LEGAL_COLLECTION, query_text=query, query_filter=query_filter, limit=top_k)
    return {
        "results": [
            {
                "collateral_type": h.metadata["collateral_type"],
                "version": h.metadata.get("version"),
                "checklist_id": h.metadata.get("checklist_id"),
                "is_mandatory": h.metadata.get("is_mandatory"),
                "text": h.document,
                "score": h.score,
            }
            for h in hits
        ]
    }


async def health(_request) -> JSONResponse:
    try:
        qdrant.get_collections()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"status": "unhealthy", "server": SERVER_NAME, "error": str(exc)},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "server": SERVER_NAME})


# See mcp-deterministic/app/server.py for why the lifespan must be
# re-attached explicitly (streamable_http_app()'s session manager task
# group never starts otherwise — every /mcp POST 500s).
mcp_asgi_app = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp_asgi_app),
    ],
    lifespan=lambda _app: mcp.session_manager.run(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
