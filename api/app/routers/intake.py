"""Tiếp nhận hồ sơ RM — phía GHI của case (tạo case, upload tài liệu, nộp
thẩm định). Tách khỏi cases.py vì file đó đã hơn 350 dòng và thuần phía đọc.

Spec: docs/superpowers/specs/2026-07-19-rm-intake-backend-design.md
"""
from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.constants import REQUIRED_DOC_TYPES
from shared.db import get_session
from shared.models import Case, Document
from shared.schemas import Actor
from shared.state import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    emit_event,
    transition_state,
)
from shared.storage import upload_bytes

router = APIRouter(prefix="/cases", tags=["intake"])

_CASE_ID_PATTERN = re.compile(r"^C(\d+)$")

ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class CreateCaseRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    product: str = Field(min_length=1)
    requested_facility: dict = Field(default_factory=dict)
    owner: str = Field(min_length=1)


def _next_case_id(session: Session) -> str:
    """Sinh case_id kiểu C09 nối tiếp số lớn nhất đang có.

    Case.case_id là primary key String KHÔNG có default (shared/models.py:56)
    — khác Document.document_id vốn có default=_uuid — nên tới giờ mọi
    case_id đều do script seed đặt tay. Server phải tự sinh.

    Advisory lock để hai request đồng thời không ra trùng số, cùng cơ chế
    emit_event dùng cho Event.seq (shared/state.py:212). Khoá theo hằng
    chuỗi 'case_id_seq' vì đây là bộ đếm toàn cục, không theo từng case.

    Bỏ qua case_id không khớp C{số} (dữ liệu thật có 'CASE-CUS-00001') —
    khuôn đặt tên vốn đã không nhất quán, regex chỉ đếm nhánh C{nn}.
    """
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext('case_id_seq'))"))

    existing = session.execute(select(Case.case_id)).scalars().all()
    numbers = [int(m.group(1)) for cid in existing if (m := _CASE_ID_PATTERN.match(cid))]
    return f"C{max(numbers, default=0) + 1:02d}"


def create_case_row(
    session: Session,
    *,
    customer_id: str,
    product: str,
    requested_facility: dict,
    owner: str,
) -> Case:
    """Tạo một Case ở DRAFT kèm audit event, trong session đang mở.

    Tách khỏi endpoint để nhánh đỏ của POST /intake/submissions
    (app/routers/routing.py) dùng lại nguyên vẹn thay vì nhân bản — hai
    đường vào cùng tạo case thì logic phải là một, nếu không sớm muộn
    cũng lệch.
    """
    case_id = _next_case_id(session)
    case = Case(
        case_id=case_id,
        customer_id=customer_id,
        product=product,
        requested_facility=requested_facility,
        owner=owner,
        state="DRAFT",
        version=1,
    )
    session.add(case)
    session.flush()

    emit_event(
        session,
        case_id=case_id,
        event_type="CASE_CREATED",
        actor=Actor(type="USER", id=owner),
        payload={"customer_id": customer_id, "product": product},
    )
    return case


@router.post("", status_code=201)
def create_case(body: CreateCaseRequest) -> dict:
    with get_session() as session:
        case = create_case_row(
            session,
            customer_id=body.customer_id,
            product=body.product,
            requested_facility=body.requested_facility,
            owner=body.owner,
        )
        return {"case_id": case.case_id, "state": case.state}


@router.post("/{case_id}/documents", status_code=201)
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
) -> dict:
    """Nhận một tài liệu, ghi lên MinIO rồi tạo row documents.

    doc_type do RM gửi lên, KHÔNG tự phân loại: muốn biết một PDF là
    financial_statement hay tax_filing thì phải đọc nội dung, mà đọc nội
    dung chính là trích xuất — tức lát 2. Giữ như vậy thì checklist chỉ
    là phép so tập hợp với REQUIRED_DOC_TYPES, không có tí LLM nào.
    """
    if doc_type not in REQUIRED_DOC_TYPES:
        raise HTTPException(422, f"doc_type không hợp lệ: {doc_type!r} (hợp lệ: {sorted(REQUIRED_DOC_TYPES)})")
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(422, f"kiểu file không được chấp nhận: {file.content_type!r}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(422, f"file quá lớn: {len(content)} bytes (tối đa {MAX_UPLOAD_BYTES})")

    digest = hashlib.sha256(content).hexdigest()

    with get_session() as session:
        if session.get(Case, case_id) is None:
            raise HTTPException(404, f"case {case_id!r} không tồn tại")

        existing = session.execute(
            select(Document).where(Document.case_id == case_id, Document.sha256 == digest)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "document_id": existing.document_id,
                "sha256": existing.sha256,
                "doc_type": existing.doc_type,
                "deduplicated": True,
            }

        row = Document(
            case_id=case_id,
            doc_type=doc_type,
            minio_key="",  # điền sau flush — minio_key cần document_id
            sha256=digest,
            review_status="PENDING",
        )
        session.add(row)
        session.flush()  # sinh document_id

        # Ghi MinIO TRƯỚC khi thoát khối get_session(): nếu MinIO hỏng thì
        # exception làm session rollback, không còn row documents mồ côi trỏ
        # tới object không tồn tại. Chiều ngược lại (object mồ côi khi ghi DB
        # lỗi) vô hại và dọn được bằng job quét sau.
        key = f"{case_id}/{row.document_id}/{file.filename}"
        try:
            upload_bytes(key=key, data=content, content_type=file.content_type)
        except Exception as exc:  # noqa: BLE001 - mọi lỗi MinIO đều là 502
            raise HTTPException(502, f"ghi MinIO thất bại: {exc}") from exc

        row.minio_key = key
        session.flush()

        return {
            "document_id": row.document_id,
            "sha256": digest,
            "doc_type": doc_type,
            "deduplicated": False,
        }


@router.get("/{case_id}/intake-status")
def intake_status(case_id: str) -> dict:
    """Checklist giấy tờ cho trang RM.

    Endpoint này tồn tại để frontend không phải nhân bản REQUIRED_DOC_TYPES
    ở phía client — giữ hằng số single-sourced trong shared/constants.py
    đúng như lý do file đó tồn tại.
    """
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(404, f"case {case_id!r} không tồn tại")

        docs = session.execute(select(Document).where(Document.case_id == case_id)).scalars().all()

        submitted = [
            {
                "doc_type": d.doc_type,
                "document_id": d.document_id,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in docs
        ]

        return {
            "state": case.state,
            "submitted": submitted,
            "missing": sorted(REQUIRED_DOC_TYPES - {d.doc_type for d in docs}),
            # can_submit theo state machine, KHÔNG theo checklist đủ/thiếu —
            # gate checklist thuộc lát 3. RM vẫn nộp được hồ sơ thiếu và
            # INTAKE_VALIDATION sẽ trả về NEED_INFO.
            "can_submit": "INTAKE_VALIDATION" in ALLOWED_TRANSITIONS.get(case.state, set()),
        }


@router.post("/{case_id}/submit")
def submit_case(case_id: str) -> dict:
    """Nộp hồ sơ sang thẩm định.

    Chạy được từ cả DRAFT lẫn NEED_INFO nên một endpoint phục vụ cả nộp
    mới lẫn bổ sung — ALLOWED_TRANSITIONS đã dựng sẵn cả hai.
    """
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(404, f"case {case_id!r} không tồn tại")

        try:
            updated = transition_state(
                session,
                case_id=case_id,
                new_state="INTAKE_VALIDATION",
                actor=Actor(type="USER", id=case.owner),
            )
        except InvalidTransitionError as exc:
            raise HTTPException(409, str(exc)) from exc

        return {"case_id": case_id, "state": updated.state}
