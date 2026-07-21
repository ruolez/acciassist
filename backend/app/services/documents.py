"""Storage and validation for client-uploaded case documents.

Files live on disk under ``settings.upload_dir`` with an opaque stored name;
the database row keeps the original filename for display and download."""

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.errors import AppError
from app.models import CaseDocument

# Extension → served content type. The whitelist covers what an injury case
# actually needs (records, bills, letters, photos of injuries/damage).
ALLOWED_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_CHUNK = 1024 * 1024

# Client-chosen document labels; the portal offers exactly this set.
DOCUMENT_LABELS = {
    "medical_bill",
    "medical_record",
    "photo",
    "insurance",
    "income",
    "other",
}


def validate_label(label: str | None) -> str | None:
    if label is None or label == "":
        return None
    if label not in DOCUMENT_LABELS:
        allowed = ", ".join(sorted(DOCUMENT_LABELS))
        raise AppError(422, "invalid_label", f"Label must be one of: {allowed}.")
    return label


def upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def document_path(doc: CaseDocument) -> Path:
    return upload_root() / doc.stored_name


def clean_filename(name: str) -> str:
    """Strip any path components and control characters from a client name."""
    base = Path(name).name
    return re.sub(r"[\x00-\x1f]", "", base)[:255] or "document"


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(set(ALLOWED_TYPES)))
        raise AppError(
            422,
            "unsupported_file_type",
            f"This file type isn't supported. Please upload one of: {allowed}.",
        )
    return ext


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """Stream the upload to disk, enforcing the size limit while reading.

    Returns (stored_name, content_type, size_bytes)."""
    original = clean_filename(file.filename or "document")
    ext = validate_extension(original)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = upload_root() / stored_name
    limit = settings.max_upload_mb * 1024 * 1024

    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise AppError(
                        413,
                        "file_too_large",
                        f"Files can be at most {settings.max_upload_mb} MB.",
                    )
                out.write(chunk)
    except AppError:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise AppError(422, "empty_file", "This file is empty.")
    return stored_name, ALLOWED_TYPES[ext], size


def delete_stored_file(doc: CaseDocument) -> None:
    document_path(doc).unlink(missing_ok=True)
