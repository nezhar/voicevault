"""Store an uploaded audio/video file and queue it for transcription.

Shared by the multipart route (POST /api/entries/upload) and upload links
(PUT /api/uploads/{id}). Synchronous: callers run it in a worker thread so a
large S3 transfer does not block the event loop.
"""

import mimetypes
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entry import Entry, SourceType
from app.models.user import User
from app.services.authz import require_project_editor
from app.services.entry_service import EntryService
from app.services.s3_service import S3Service

MAX_FILENAME_LENGTH = 255
STORAGE_UNAVAILABLE = "File storage is unavailable; try the upload again"


def supported_formats() -> list[str]:
    return settings.supported_audio_formats + settings.supported_video_formats


def clean_filename(filename: str | None) -> str:
    """Base name only (clients may send a path); 400 when missing or too long."""

    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        raise HTTPException(status_code=400, detail="A file name is required")
    if len(name) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"File name is too long (maximum {MAX_FILENAME_LENGTH} characters)",
        )
    return name


def file_extension(filename: str) -> str:
    """Lowercase extension of a supported audio/video file; 400 otherwise."""

    stem, dot, extension = filename.rpartition(".")
    extension = extension.lower()
    if not dot or not stem or extension not in supported_formats():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported: {', '.join(supported_formats())}",
        )
    return extension


def default_title(filename: str) -> str:
    stem = filename.rpartition(".")[0].strip()
    return (stem or filename)[:255]


def check_upload_size(size: int) -> None:
    if size > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_upload_size} bytes.",
        )


def storage_content_type(extension: str, declared: str | None) -> str:
    """Content type stored with the object and later served by /audio.

    Never trust a client-declared type outright: the audio route echoes it back
    to browsers, so only audio/video types are kept.
    """

    for candidate in (mimetypes.guess_type(f"file.{extension}")[0], declared):
        if candidate and candidate.split("/", 1)[0] in ("audio", "video"):
            return candidate.split(";", 1)[0].strip()
    return "application/octet-stream"


def _discard_entry(db: Session, entry_id: UUID) -> None:
    """Remove an entry whose file never reached storage, so it can't linger as NEW."""

    try:
        db.rollback()
        db.query(Entry).filter(Entry.id == entry_id).delete()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not remove entry {} after a failed upload", entry_id)


def ingest_upload(
    db: Session,
    user: User,
    *,
    title: str,
    filename: str | None,
    fileobj: BinaryIO,
    size: int,
    content_type: str | None = None,
    language: str | None = None,
    project_id: UUID | None = None,
) -> Entry:
    """Validate, create the entry, store the file, and queue it for the ASR worker.

    The worker only picks up uploads once file_path is set, so the entry is
    removed again if storage fails.
    """

    filename = clean_filename(filename)
    extension = file_extension(filename)
    check_upload_size(size)
    if project_id is not None:
        require_project_editor(db, project_id, user)

    try:
        s3_service = S3Service()
    except Exception:
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE) from None

    entry_service = EntryService(db)
    entry = entry_service.create_entry(
        title=title,
        source_type=SourceType.UPLOAD,
        filename=filename,
        language=language,
        user_id=user.id,
        project_id=project_id,
        file_size_bytes=size,
    )
    entry_id = entry.id
    s3_key = f"uploads/{entry_id}.{extension}"

    try:
        if not s3_service.upload_file(
            fileobj,
            s3_key,
            content_type=storage_content_type(extension, content_type),
        ):
            raise RuntimeError("S3 upload failed")
        entry = entry_service.update_entry_file_path(entry_id, s3_key)
        if entry is None:
            raise RuntimeError("Entry disappeared during upload")
    except Exception as exc:
        logger.error("Failed to store upload for entry {}: {}", entry_id, exc)
        s3_service.delete_file(s3_key)
        _discard_entry(db, entry_id)
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE) from None

    return entry
