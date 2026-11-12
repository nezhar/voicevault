"""Upload links: created by a signed-in user or PAT, used once with a link token.

POST/GET under /api/entries/upload-sessions authenticate like every other
entries route (PAT scopes entries:write / entries:read). /api/uploads/{id}
accepts only the link's own token (Bearer vvupl_...), never a session or PAT,
so it can serve curl and the browser upload page without a login. It is
deliberately absent from the PAT scope map in app/core/auth.py.
"""

import hashlib
from tempfile import SpooledTemporaryFile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.timeutils import utcnow
from app.db.database import get_db
from app.models.personal_access_token import PersonalAccessToken
from app.models.schemas import (
    EntryResponse,
    UploadCompleted,
    UploadLinkInfo,
    UploadSessionCreate,
    UploadSessionCreated,
    UploadSessionResponse,
)
from app.models.upload_session import UploadSession, UploadState
from app.models.user import User
from app.services.authz import require_project_editor
from app.services.upload_service import (
    MAX_FILENAME_LENGTH,
    check_upload_size,
    clean_filename,
    default_title,
    file_extension,
    ingest_upload,
    supported_formats,
)
from app.services.upload_session_service import UploadSessionService, upload_state

router = APIRouter()

# Received bytes stay in memory up to this size, then spill to a temp file.
SPOOL_MEMORY_BYTES = 8 * 1024 * 1024

_INVALID_LINK = HTTPException(
    status_code=401,
    detail="This upload link is invalid or no longer valid",
    headers={"WWW-Authenticate": "Bearer"},
)


def _session_fields(session: UploadSession) -> dict:
    return {
        "id": session.id,
        "state": upload_state(session),
        "title": session.title,
        "filename": session.filename,
        "language": session.language,
        "project_id": session.project_id,
        "expected_size_bytes": session.expected_size_bytes,
        "max_bytes": _size_limit(session),
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "completed_at": session.completed_at,
        "entry_id": session.entry_id,
    }


def _size_limit(session: UploadSession) -> int:
    if session.expected_size_bytes:
        return min(settings.max_upload_size, session.expected_size_bytes)
    return settings.max_upload_size


def _public_base_url() -> str:
    if not settings.public_base_url:
        raise HTTPException(
            status_code=503,
            detail="Upload links are unavailable: PUBLIC_BASE_URL is not configured",
        )
    return settings.public_base_url.rstrip("/")


@router.post(
    "/entries/upload-sessions",
    response_model=UploadSessionCreated,
    status_code=201,
)
async def create_upload_session(
    data: UploadSessionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a single-use upload link. Unknown file details may be left out."""

    base_url = _public_base_url()
    filename = None
    if data.filename is not None:
        filename = clean_filename(data.filename)
        file_extension(filename)
    if data.size_bytes is not None:
        check_upload_size(data.size_bytes)
    if data.project_id is not None:
        require_project_editor(db, data.project_id, current_user)

    pat = getattr(request.state, "pat", None)
    session, token = UploadSessionService(db).create(
        user_id=current_user.id,
        pat_id=pat.id if pat is not None else None,
        title=data.title,
        filename=filename,
        language=data.language,
        project_id=data.project_id,
        expected_size_bytes=data.size_bytes,
        expected_sha256=data.sha256,
    )
    return UploadSessionCreated(
        **_session_fields(session),
        token=token,
        upload_url=f"{base_url}/api/uploads/{session.id}",
        # The fragment never reaches a server or its access logs.
        browser_url=f"{base_url}/upload#{session.id}.{token}",
    )


@router.get(
    "/entries/upload-sessions/{session_id}",
    response_model=UploadSessionResponse,
)
async def get_upload_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """State of one of your upload links."""

    session = UploadSessionService(db).get_for_owner(session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return UploadSessionResponse(**_session_fields(session))


def _bearer(request: Request) -> str | None:
    values = request.headers.getlist("authorization")
    parts = values[0].split() if len(values) == 1 else []
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _resolve_link(session_id: UUID, request: Request, db: Session) -> UploadSession:
    session = UploadSessionService(db).resolve(session_id, _bearer(request))
    if session is None:
        raise _INVALID_LINK
    return session


def _authorize_owner(db: Session, session: UploadSession) -> User:
    """Re-check, at use time, everything that allowed creating the link."""

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise _INVALID_LINK
    if session.pat_id is not None:
        pat = db.get(PersonalAccessToken, session.pat_id)
        if (
            pat is None
            or pat.revoked_at is not None
            or (pat.expires_at is not None and pat.expires_at <= utcnow())
        ):
            raise _INVALID_LINK
    if session.project_id is not None:
        require_project_editor(db, session.project_id, user)
    return user


def _refuse_unusable(session: UploadSession) -> None:
    state = upload_state(session)
    if state == UploadState.COMPLETED:
        # Names the entry so a client whose first response got lost can find it.
        raise HTTPException(
            status_code=409,
            detail=f"This upload link was already used (entry {session.entry_id})",
        )
    if state == UploadState.UPLOADING:
        raise HTTPException(
            status_code=409,
            detail="An upload for this link is already in progress",
        )
    if state == UploadState.EXPIRED:
        raise HTTPException(
            status_code=410,
            detail="This upload link has expired; ask for a new one",
        )


@router.get("/uploads/{session_id}", response_model=UploadLinkInfo)
async def get_upload_link(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Link details for the browser upload page (link token only)."""

    session = _resolve_link(session_id, request, db)
    if upload_state(session) != UploadState.COMPLETED:
        _authorize_owner(db, session)
    return UploadLinkInfo(
        **_session_fields(session),
        supported_formats=supported_formats(),
    )


@router.put("/uploads/{session_id}", response_model=UploadCompleted)
async def upload_to_link(
    session_id: UUID,
    request: Request,
    filename: str | None = Query(default=None, max_length=MAX_FILENAME_LENGTH),
    db: Session = Depends(get_db),
):
    """Receive the raw file body for an upload link and create its entry.

    Nothing is committed until the whole body has arrived and matches the
    declared size/checksum, so an interrupted upload can simply be retried
    with the same link. A retry after success gets 409 instead of a duplicate.
    """

    session = _resolve_link(session_id, request, db)
    _refuse_unusable(session)
    user = _authorize_owner(db, session)

    # Everything that can be rejected without the body is rejected first.
    name = clean_filename(filename or session.filename)
    file_extension(name)
    limit = _size_limit(session)
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            declared = int(declared_length)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid Content-Length",
            ) from None
        if declared > limit:
            raise _too_large(limit)

    digest = hashlib.sha256()
    received = 0
    spool = SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES)
    try:
        try:
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    raise _too_large(limit)
                digest.update(chunk)
                spool.write(chunk)
        except ClientDisconnect:
            logger.info("Upload {} interrupted after {} bytes", session.id, received)
            raise HTTPException(
                status_code=400,
                detail="The upload was interrupted; retry with the same link",
            ) from None

        if received == 0:
            raise HTTPException(status_code=400, detail="The upload was empty")
        if (
            session.expected_size_bytes is not None
            and received != session.expected_size_bytes
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Received {received} bytes but {session.expected_size_bytes} were "
                    "expected; the upload was incomplete. Retry with the same link"
                ),
            )
        if (
            session.expected_sha256 is not None
            and digest.hexdigest() != session.expected_sha256
        ):
            raise HTTPException(
                status_code=400,
                detail="Checksum mismatch; the file was corrupted. Retry with the same link",
            )

        service = UploadSessionService(db)
        if not service.claim(session):
            _refuse_unusable(session)
            raise HTTPException(status_code=409, detail="This upload link is in use")

        spool.seek(0)
        try:
            entry = await run_in_threadpool(
                ingest_upload,
                db,
                user,
                title=session.title or default_title(name),
                filename=name,
                fileobj=spool,
                size=received,
                content_type=request.headers.get("content-type"),
                language=session.language,
                project_id=session.project_id,
            )
        except Exception:
            # Not on cancellation: the worker thread may still finish storing,
            # and a stale claim frees itself after STALE_CLAIM_AFTER anyway.
            service.release(session)
            raise
        service.complete(session, entry.id)
    finally:
        spool.close()

    return UploadCompleted(
        upload_id=session.id,
        entry=EntryResponse.model_validate(entry),
    )


def _too_large(limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"File too large for this upload link (maximum {limit} bytes)",
    )
