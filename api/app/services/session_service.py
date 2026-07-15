import hashlib
import secrets
from datetime import timedelta

from app.core.timeutils import utcnow
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_session import AuthSession

SESSION_COOKIE_NAME = "voicevault_session"


def hash_session_token(token: str) -> str:
    """Sessions are stored hashed so a leaked database cannot be replayed
    as cookies."""

    return hashlib.sha256(token.encode()).hexdigest()


class SessionService:
    def __init__(self, db: Session):
        self.db = db

    def create_session(self, user_id: UUID) -> tuple[AuthSession, str]:
        """Create a session and opportunistically purge expired ones.

        Returns the stored row and the raw token that goes into the cookie;
        only the token's hash ever touches the database.
        """

        self.db.query(AuthSession).filter(
            AuthSession.expires_at < utcnow(),
        ).delete(synchronize_session=False)

        token = secrets.token_urlsafe(32)
        session = AuthSession(
            id=hash_session_token(token),
            user_id=user_id,
            expires_at=utcnow() + timedelta(hours=settings.session_lifetime_hours),
        )
        self.db.add(session)
        self.db.commit()
        return session, token

    def get_valid_session(self, token: str) -> AuthSession | None:
        session = (
            self.db.query(AuthSession)
            .filter(AuthSession.id == hash_session_token(token))
            .first()
        )
        if not session:
            return None
        if session.expires_at < utcnow():
            self.db.delete(session)
            self.db.commit()
            return None
        return session

    def delete_session(self, token: str) -> None:
        self.db.query(AuthSession).filter(
            AuthSession.id == hash_session_token(token),
        ).delete(synchronize_session=False)
        self.db.commit()
