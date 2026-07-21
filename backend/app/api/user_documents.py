from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.errors import AppError
from app.models import Case, CaseDocument
from app.schemas import CaseDocumentOut
from app.services.documents import (
    clean_filename,
    delete_stored_file,
    document_path,
    save_upload,
)

router = APIRouter()


async def _my_case(db: DbSession, case_id: int, user_id: int) -> Case:
    case = await db.scalar(select(Case).where(Case.id == case_id, Case.user_id == user_id))
    if case is None:
        raise AppError(404, "not_found", "Case not found")
    return case


async def _my_document(
    db: DbSession, case_id: int, doc_id: int, user_id: int
) -> CaseDocument:
    await _my_case(db, case_id, user_id)
    doc = await db.get(CaseDocument, doc_id)
    if doc is None or doc.case_id != case_id:
        raise AppError(404, "not_found", "Document not found")
    return doc


@router.get("/cases/{case_id}/documents", response_model=list[CaseDocumentOut])
async def list_documents(
    case_id: int, user: CurrentUser, db: DbSession
) -> list[CaseDocument]:
    await _my_case(db, case_id, user.id)
    rows = await db.scalars(
        select(CaseDocument)
        .where(CaseDocument.case_id == case_id)
        .order_by(CaseDocument.created_at.desc())
    )
    return list(rows)


@router.post(
    "/cases/{case_id}/documents", response_model=CaseDocumentOut, status_code=201
)
async def upload_document(
    case_id: int, file: UploadFile, user: CurrentUser, db: DbSession
) -> CaseDocument:
    case = await _my_case(db, case_id, user.id)
    count = await db.scalar(
        select(func.count()).select_from(CaseDocument).where(CaseDocument.case_id == case.id)
    )
    if count is not None and count >= settings.max_documents_per_case:
        raise AppError(
            422,
            "too_many_documents",
            f"A case can hold at most {settings.max_documents_per_case} documents.",
        )
    stored_name, content_type, size = await save_upload(file)
    doc = CaseDocument(
        case_id=case.id,
        original_name=clean_filename(file.filename or "document"),
        content_type=content_type,
        size_bytes=size,
        stored_name=stored_name,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/cases/{case_id}/documents/{doc_id}/download")
async def download_document(
    case_id: int, doc_id: int, user: CurrentUser, db: DbSession
) -> FileResponse:
    doc = await _my_document(db, case_id, doc_id, user.id)
    path = document_path(doc)
    if not path.exists():
        raise AppError(404, "file_missing", "The stored file is missing.")
    return FileResponse(path, media_type=doc.content_type, filename=doc.original_name)


@router.delete("/cases/{case_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    case_id: int, doc_id: int, user: CurrentUser, db: DbSession
) -> None:
    doc = await _my_document(db, case_id, doc_id, user.id)
    delete_stored_file(doc)
    await db.delete(doc)
    await db.commit()
