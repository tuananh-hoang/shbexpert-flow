from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .io import write_json

REFERENCE_SOURCES = [
    {
        "source_id": "VSIC_2025",
        "url": "https://chinhphu.vn/?docid=215475&pageid=27160",
        "publisher": "Cổng Thông tin điện tử Chính phủ",
        "filename": "vsic_2025.html",
        "usage": "taxonomy_reference",
    },
    {
        "source_id": "NSO_PXWEB",
        "url": "https://pxweb.nso.gov.vn/api/v1/vi",
        "publisher": "National Statistics Office of Vietnam",
        "filename": "nso_pxweb_root.json",
        "usage": "aggregate_statistics_catalog",
    },
    {
        "source_id": "ACCOUNTING_TT133",
        "url": "https://congbao.chinhphu.vn/van-ban/thong-tu-so-133-2016-tt-btc-21048/15524.htm",
        "publisher": "Công báo Chính phủ",
        "filename": "accounting_tt133.html",
        "usage": "statement_line_item_reference",
    },
    {
        "source_id": "SME_ND80",
        "url": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-80-2021-nd-cp-34251.htm",
        "publisher": "Công báo Chính phủ",
        "filename": "sme_nd80.html",
        "usage": "sme_segmentation_reference",
    },
]


def sync_reference_snapshots(output: Path, timeout_seconds: int = 30) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    entries: list[dict[str, Any]] = []
    for source in REFERENCE_SOURCES:
        entry = dict(source)
        request = Request(source["url"], headers={"User-Agent": "DashmintSyntheticData/0.1 (+hackathon research snapshot)"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "")
                status = response.status
            target = output / source["filename"]
            target.write_bytes(payload)
            entry.update(
                {
                    "status": "fetched",
                    "http_status": status,
                    "content_type": content_type,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "retrieved_at": retrieved_at,
                }
            )
        except Exception as exc:
            entry.update({"status": "failed", "retrieved_at": retrieved_at, "error": f"{type(exc).__name__}: {exc}"})
        entries.append(entry)
    entries.append(
        {
            "source_id": "SHB_PRODUCT_REGISTRY",
            "url": "https://www.shb.com.vn/category/khach-hang-doanh-nghiep/",
            "publisher": "SHB",
            "usage": "manual_product_reference_only",
            "status": "manual_curate_only",
            "robots_decision": "Do not mirror or use for model training; curate short factual registry manually.",
            "retrieved_at": retrieved_at,
        }
    )
    manifest = {
        "schema_version": "0.1",
        "retrieved_at": retrieved_at,
        "offline_after_snapshot": True,
        "sources": entries,
    }
    write_json(output / "source_manifest.json", manifest)
    return manifest
