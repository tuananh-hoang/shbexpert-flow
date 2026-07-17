"""MinIO helper — thin wrapper so seed scripts / api don't each reimplement
bucket bootstrap and presigned URLs. Per overview.md/data-flow.md §1:
Postgres holds metadata + hash + pointer, MinIO holds the file bytes; the
evidence drawer opens documents via presigned URL, never base64-in-state.
"""
from __future__ import annotations

import hashlib
import os
from datetime import timedelta

from minio import Minio

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
# Presigned URLs embed the endpoint host in the signed URL itself. Using the
# internal Docker DNS name ("minio") there produces a URL the *browser*
# (running outside the compose network) can never resolve — only
# server-to-server calls (api/worker) should use MINIO_ENDPOINT directly.
# MINIO_PUBLIC_ENDPOINT defaults to the host-bound port from
# docker-compose.yml (127.0.0.1:9000) so evidence-drawer links opened by a
# browser on the same dev machine actually work.
MINIO_PUBLIC_ENDPOINT = os.environ.get("MINIO_PUBLIC_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "shbexpert-documents")


# Pinned explicitly (single-node MinIO's default) so presigned_get_object()
# never triggers a GetBucketLocation lookup against MINIO_PUBLIC_ENDPOINT —
# that endpoint is only resolvable from a *browser*, not from inside this
# container, so the SDK's own auto-lookup would fail with
# ConnectionRefusedError before it ever got to signing the URL.
MINIO_REGION = "us-east-1"


def get_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        secure=False,  # internal Docker network, no TLS needed
        region=MINIO_REGION,
    )


def _public_client() -> Minio:
    """Separate client instance whose endpoint is the browser-reachable one
    — only used to compute presigned URLs, never for put/get_object calls
    (those go through get_client() over the internal Docker network)."""
    return Minio(
        MINIO_PUBLIC_ENDPOINT,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        secure=False,
        region=MINIO_REGION,
    )


def ensure_bucket(client: Minio | None = None) -> None:
    client = client or get_client()
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Uploads `data` under `key` and returns its sha256 hex digest — the
    hash Documents.sha256 stores per FR-02 (detect silent replacement)."""
    import io

    client = get_client()
    ensure_bucket(client)
    client.put_object(MINIO_BUCKET, key, io.BytesIO(data), length=len(data), content_type=content_type)
    return hashlib.sha256(data).hexdigest()


def presigned_url(key: str, expires_minutes: int = 15) -> str:
    """Returns a URL signed for MINIO_PUBLIC_ENDPOINT — safe to hand to the
    browser (evidence drawer). See MINIO_PUBLIC_ENDPOINT above for why this
    must NOT reuse the internal get_client()."""
    return _public_client().presigned_get_object(MINIO_BUCKET, key, expires=timedelta(minutes=expires_minutes))


def get_object_bytes(key: str) -> bytes:
    """Reads an object's full bytes over the internal Docker network — used
    by api's same-origin PDF proxy endpoint (GET
    /cases/{id}/documents/{id}/file) so the in-app Evidence Viewer
    (react-pdf) never needs a cross-origin fetch to MinIO directly, which
    would need bucket CORS configuration. Fine for the small (single-page)
    seed PDFs this project generates; a large-file streaming variant would
    use get_object()'s stream instead of read()+close()+release_conn()."""
    client = get_client()
    response = client.get_object(MINIO_BUCKET, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
