"""Small cross-service constants — values both `api` and `worker` need to
agree on, without either importing the other's package. Started with
REQUIRED_DOC_TYPES: previously defined only inside
worker/app/graph/decision.py (where gate G1 checks it), but the Document
Completeness dashboard widget needs the exact same list on the `api` side
too — a single source here means the two can never silently drift apart.
"""
from __future__ import annotations

REQUIRED_DOC_TYPES: frozenset[str] = frozenset(
    {"financial_statement", "tax_filing", "valuation_certificate", "business_registration"}
)
