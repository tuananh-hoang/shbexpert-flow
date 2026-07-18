"""JSONL read/write helpers shared by both eval variants and the aggregator.

Deliberately stdlib-only (no pandas/jsonlines) — eval/README.md explains why."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
