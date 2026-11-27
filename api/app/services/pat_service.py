import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy import or_, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core.capabilities import Capability
from app.core.timeutils import utcnow
from app.models.personal_access_token import PersonalAccessToken
from app.models.user import User

PAT_MARKER = "vvpat_"
DISPLAY_PREFIX_LENGTH = 16
LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)


# Every capability a token can carry (a token never exceeds its owner anyway).
ALL_PAT_PERMISSIONS = frozenset(cap.value for cap in Capability)


class PATValidationFailure(str, Enum):
    MALFORMED = "malformed"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INACTIVE_USER = "inactive_user"


@dataclass(frozen=True)
class PATValidationResult:
    token: PersonalAccessToken | None = None
    user: User | None = None
    failure: PATValidationFailure | None = None


def hash_pat(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def safe_token_prefix(token: str) -> str | None:
    if not token.startswith(PAT_MARKER) or len(token) < DISPLAY_PREFIX_LENGTH:
        return None
    return token[:DISPLAY_PREFIX_LENGTH]


LIKE_ESCAPE = "\\"


def escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input matches literally.

    Pass ``escape=LIKE_ESCAPE`` to the ``like``/``ilike`` call using the result.
    """

    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


class PATNotEditable(Exception):
    """Only active tokens can be changed.

    Moving an expired token's expiry into the future would revive a credential
    the owner may have stopped guarding, and a revoked one is dead for good.
    """


class PATService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        permissions: list[str],
        expires_at: datetime | None,
        project_ids: list[UUID] | None = None,
        source: str = "manual",
        oauth_client_id: str | None = None,
        commit: bool = True,
    ) -> tuple[PersonalAccessToken, str]:
        raw_token = PAT_MARKER + secrets.token_urlsafe(32)
        pat = PersonalAccessToken(
            user_id=user_id,
            name=name.strip(),
            token_hash=hash_pat(raw_token),
            token_prefix=raw_token[:DISPLAY_PREFIX_LENGTH],
            permissions=sorted(set(permissions)),
            expires_at=expires_at,
            project_ids=(
                sorted({str(pid) for pid in project_ids})
                if project_ids is not None
                else None
            ),
            source=source,
            oauth_client_id=oauth_client_id,
        )
        self.db.add(pat)
        if commit:
            self.db.commit()
            self.db.refresh(pat)
        else:
            self.db.flush()
        return pat, raw_token

    def list_for_user(self, user_id: UUID) -> list[PersonalAccessToken]:
        return (
            self.db.query(PersonalAccessToken)
            .filter(PersonalAccessToken.user_id == user_id)
            .order_by(PersonalAccessToken.created_at.desc())
            .all()
        )

    def list_all(
        self,
        *,
        user_id: UUID | None = None,
        name: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[tuple[PersonalAccessToken, User]], int]:
        query = self.db.query(PersonalAccessToken, User).join(
            User,
            User.id == PersonalAccessToken.user_id,
        )
        if user_id is not None:
            query = query.filter(PersonalAccessToken.user_id == user_id)
        if name and name.strip():
            pattern = f"%{escape_like(name.strip())}%"
            query = query.filter(
                PersonalAccessToken.name.ilike(pattern, escape=LIKE_ESCAPE),
            )

        now = utcnow()
        if status == "active":
            query = query.filter(
                PersonalAccessToken.revoked_at.is_(None),
                or_(
                    PersonalAccessToken.expires_at.is_(None),
                    PersonalAccessToken.expires_at > now,
                ),
            )
        elif status == "expired":
            query = query.filter(
                PersonalAccessToken.revoked_at.is_(None),
                PersonalAccessToken.expires_at.is_not(None),
                PersonalAccessToken.expires_at <= now,
            )
        elif status == "revoked":
            query = query.filter(PersonalAccessToken.revoked_at.is_not(None))

        total = query.count()
        rows = (
            query.order_by(PersonalAccessToken.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def revoke(self, token_id: UUID, user_id: UUID | None = None) -> bool:
        """Revoke a token; with user_id only that user's token matches (owner view).

        Returns False when nothing matched. Revoking twice is a no-op.
        """

        query = self.db.query(PersonalAccessToken).filter(
            PersonalAccessToken.id == token_id,
        )
        if user_id is not None:
            query = query.filter(PersonalAccessToken.user_id == user_id)
        pat = query.first()
        if pat is None:
            return False
        if pat.revoked_at is None:
            pat.revoked_at = utcnow()
            self.db.commit()
        return True

    def update(
        self,
        token_id: UUID,
        user_id: UUID,
        changes: dict,
    ) -> PersonalAccessToken | None:
        """Apply name/expires_at changes to an owned, active token.

        Returns None when the token is not the user's; raises PATNotEditable
        for expired or revoked tokens. An empty ``changes`` is a no-op.
        """

        pat = (
            self.db.query(PersonalAccessToken)
            .filter(
                PersonalAccessToken.id == token_id,
                PersonalAccessToken.user_id == user_id,
            )
            .first()
        )
        if pat is None:
            return None
        if pat.revoked_at is not None or (
            pat.expires_at is not None and pat.expires_at <= utcnow()
        ):
            raise PATNotEditable()
        if "name" in changes and changes["name"] is not None:
            pat.name = changes["name"]
        if "expires_at" in changes:
            pat.expires_at = changes["expires_at"]
        if changes:
            self.db.commit()
            self.db.refresh(pat)
        return pat

    def revoke_all_for_user(self, user_id: UUID, *, commit: bool = True) -> int:
        """Revoke every live token of a user. commit=False joins the caller's transaction."""

        count = (
            self.db.query(PersonalAccessToken)
            .filter(
                PersonalAccessToken.user_id == user_id,
                PersonalAccessToken.revoked_at.is_(None),
            )
            .update(
                {PersonalAccessToken.revoked_at: utcnow()},
                synchronize_session=False,
            )
        )
        if commit:
            self.db.commit()
        return count

    def touch_last_used(self, pat: PersonalAccessToken) -> bool:
        """Record usage, at most once per LAST_USED_WRITE_INTERVAL.

        Call this only once the token itself has been authorized, so that a
        probe refused by _enforce_pat_permission - a missing scope, the admin
        area, an interactive-only route - leaves no trace of activity. A request
        that clears the token gate and is then refused on the resource (someone
        else's entry, say) does still count: the caller held a usable token, and
        per-object checks live in the routes, past this point.

        The write goes through a separate connection so the request-scoped
        session is not committed (and its loaded objects not expired) in the
        middle of authentication.
        """

        now = utcnow()
        cutoff = now - LAST_USED_WRITE_INTERVAL
        if pat.last_used_at is not None and pat.last_used_at > cutoff:
            return False
        # The cutoff is repeated in the UPDATE so the interval holds under load:
        # concurrent requests all read the same stale value, and without it they
        # would all write. The loser sees rowcount 0 and leaves the row alone.
        with self.db.get_bind().begin() as connection:
            written = connection.execute(
                update(PersonalAccessToken)
                .where(
                    PersonalAccessToken.id == pat.id,
                    or_(
                        PersonalAccessToken.last_used_at.is_(None),
                        PersonalAccessToken.last_used_at <= cutoff,
                    ),
                )
                .values(last_used_at=now),
            ).rowcount
        if not written:
            return False
        set_committed_value(pat, "last_used_at", now)
        return True

    def validate(self, raw_token: str) -> PATValidationResult:
        """Resolve a raw token to (token, user) without writing anything."""

        if (
            not raw_token.startswith(PAT_MARKER)
            or len(raw_token) <= len(PAT_MARKER) + 20
        ):
            return PATValidationResult(failure=PATValidationFailure.MALFORMED)

        row = (
            self.db.query(PersonalAccessToken, User)
            .join(User, User.id == PersonalAccessToken.user_id)
            .filter(PersonalAccessToken.token_hash == hash_pat(raw_token))
            .first()
        )
        if row is None:
            return PATValidationResult(failure=PATValidationFailure.INVALID)

        pat, user = row
        if pat.revoked_at is not None:
            return PATValidationResult(failure=PATValidationFailure.REVOKED)
        if pat.expires_at is not None and pat.expires_at <= utcnow():
            return PATValidationResult(failure=PATValidationFailure.EXPIRED)
        if not user.is_active:
            return PATValidationResult(failure=PATValidationFailure.INACTIVE_USER)
        return PATValidationResult(token=pat, user=user)
