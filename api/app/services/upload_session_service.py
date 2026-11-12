"""Single-use upload links: creation, token checks, and the claim protocol."""

import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutils import utcnow
from app.models.upload_session import UploadSession, UploadState
from app.services.pat_service import hash_pat

UPLOAD_TOKEN_MARKER = "vvupl_"
MAX_PENDING_PER_USER = 20
# Expired links are kept this long so status checks still answer, then purged.
PURGE_AFTER = timedelta(hours=24)
# A claim this old belongs to a request that died while storing the file
# (the proxy gives up on it long before); the link may then be used again.
STALE_CLAIM_AFTER = timedelta(minutes=30)


def _claim_is_live(session: UploadSession, now: datetime) -> bool:
    return (
        session.claimed_at is not None and session.claimed_at > now - STALE_CLAIM_AFTER
    )


def upload_state(session: UploadSession, now: datetime | None = None) -> UploadState:
    now = now or utcnow()
    if session.completed_at is not None:
        return UploadState.COMPLETED
    if _claim_is_live(session, now):
        return UploadState.UPLOADING
    if session.expires_at <= now:
        return UploadState.EXPIRED
    return UploadState.PENDING


class UploadSessionService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        pat_id: UUID | None,
        title: str | None,
        filename: str | None,
        language: str | None,
        project_id: UUID | None,
        expected_size_bytes: int | None,
        expected_sha256: str | None,
    ) -> tuple[UploadSession, str]:
        """Create a link and return it with its raw token (never stored)."""

        now = utcnow()
        self.db.query(UploadSession).filter(
            UploadSession.user_id == user_id,
            UploadSession.expires_at < now - PURGE_AFTER,
        ).delete(synchronize_session=False)

        pending = (
            self.db.query(func.count(UploadSession.id))
            .filter(
                UploadSession.user_id == user_id,
                UploadSession.completed_at.is_(None),
                UploadSession.expires_at > now,
            )
            .scalar()
        )
        if pending >= MAX_PENDING_PER_USER:
            self.db.commit()  # keep the purge
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many open upload links (maximum {MAX_PENDING_PER_USER}); "
                    "use or let some expire first"
                ),
            )

        raw_token = UPLOAD_TOKEN_MARKER + secrets.token_urlsafe(32)
        session = UploadSession(
            user_id=user_id,
            pat_id=pat_id,
            token_hash=hash_pat(raw_token),
            title=title,
            filename=filename,
            language=language,
            project_id=project_id,
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha256.lower() if expected_sha256 else None,
            created_at=now,
            expires_at=now + timedelta(minutes=settings.upload_session_ttl_minutes),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session, raw_token

    def get_for_owner(self, session_id: UUID, user_id: UUID) -> UploadSession | None:
        return (
            self.db.query(UploadSession)
            .filter(UploadSession.id == session_id, UploadSession.user_id == user_id)
            .first()
        )

    def resolve(self, session_id: UUID, raw_token: str | None) -> UploadSession | None:
        """The session the token belongs to, or None for any mismatch."""

        if not raw_token or not raw_token.startswith(UPLOAD_TOKEN_MARKER):
            return None
        session = self.db.get(UploadSession, session_id)
        if session is None:
            return None
        if not secrets.compare_digest(session.token_hash, hash_pat(raw_token)):
            return None
        return session

    def claim(self, session: UploadSession) -> bool:
        """Atomically reserve the link for one request; False if another holds it."""

        now = utcnow()
        claimed = self.db.execute(
            update(UploadSession)
            .where(
                UploadSession.id == session.id,
                UploadSession.completed_at.is_(None),
                or_(
                    UploadSession.claimed_at.is_(None),
                    UploadSession.claimed_at <= now - STALE_CLAIM_AFTER,
                ),
            )
            .values(claimed_at=now)
            .execution_options(synchronize_session=False),
        ).rowcount
        self.db.commit()
        self.db.refresh(session)
        return claimed == 1

    def complete(self, session: UploadSession, entry_id: UUID) -> None:
        session.completed_at = utcnow()
        session.entry_id = entry_id
        self.db.commit()

    def release(self, session: UploadSession) -> None:
        """Make the link usable again after a failed attempt."""

        self.db.rollback()
        self.db.execute(
            update(UploadSession)
            .where(UploadSession.id == session.id, UploadSession.completed_at.is_(None))
            .values(claimed_at=None)
            .execution_options(synchronize_session=False),
        )
        self.db.commit()
