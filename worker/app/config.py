"""Central place worker reads its own environment — one import site instead
of scattering `os.environ.get(...)` across agents/graph modules."""
from __future__ import annotations

import os

from shared.queue import ANALYZE_QUEUE, progress_channel  # re-exported for worker call sites

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL")  # shared.db.engine already reads this too

MCP_DETERMINISTIC_URL = os.environ.get("MCP_DETERMINISTIC_URL", "http://mcp-deterministic:8200/mcp")
MCP_RAG_URL = os.environ.get("MCP_RAG_URL", "http://mcp-rag:8201/mcp")
MCP_EXTERNAL_URL = os.environ.get("MCP_EXTERNAL_URL", "http://mcp-external:8202/mcp")
MCP_STATE_URL = os.environ.get("MCP_STATE_URL", "http://mcp-state:8203/mcp")

__all__ = [
    "ANALYZE_QUEUE",
    "progress_channel",
    "REDIS_URL",
    "DATABASE_URL",
    "MCP_DETERMINISTIC_URL",
    "MCP_RAG_URL",
    "MCP_EXTERNAL_URL",
    "MCP_STATE_URL",
]
