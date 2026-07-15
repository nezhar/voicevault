from app.core.timeutils import utcnow

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.user import User

SYSTEM_USER_EMAIL = "local@system.invalid"


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_system_user(self) -> User:
        """Single shared identity used by the none/token auth modes."""

        user = self.db.query(User).filter(User.is_system.is_(True)).first()
        if user:
            return user

        user = User(
            email=SYSTEM_USER_EMAIL,
            display_name="Local User",
            is_system=True,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            # another replica created it concurrently (unique email)
            self.db.rollback()
            user = self.db.query(User).filter(User.is_system.is_(True)).first()
            if user is None:
                raise
            return user
        self.db.refresh(user)
        return user

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email.strip().lower()).first()

    def provision_oidc_user(
        self,
        issuer: str,
        subject: str,
        email: str,
        display_name: str | None,
    ) -> User:
        """Find by (issuer, subject) or create; refresh email/name on every login."""

        normalized_email = email.strip().lower()
        user = (
            self.db.query(User)
            .filter(User.issuer == issuer, User.subject == subject)
            .first()
        )

        if user:
            user.email = normalized_email
            user.display_name = display_name or normalized_email
            user.last_login_at = utcnow()
        else:
            user = User(
                issuer=issuer,
                subject=subject,
                email=normalized_email,
                display_name=display_name or normalized_email,
                last_login_at=utcnow(),
            )
            self.db.add(user)

        self.db.commit()
        self.db.refresh(user)
        return user

    def assign_orphan_entries(self, owner: User) -> int:
        """Startup helper (none/token modes): give ownerless entries to the system user."""

        updated = (
            self.db.query(Entry)
            .filter(Entry.user_id.is_(None))
            .update({Entry.user_id: owner.id}, synchronize_session=False)
        )
        if updated:
            self.db.commit()
            logger.info(f"Assigned {updated} ownerless entries to {owner.email}")
        return updated

    def claim_legacy_entries(self, owner: User) -> int:
        """INITIAL_OWNER_EMAIL takeover: ownerless entries plus the system user's entries.

        Idempotent — after the first takeover there is nothing left to match.
        """

        system_user = self.get_or_create_system_user()
        updated = (
            self.db.query(Entry)
            .filter(or_(Entry.user_id.is_(None), Entry.user_id == system_user.id))
            .update({Entry.user_id: owner.id}, synchronize_session=False)
        )
        if updated:
            self.db.commit()
            logger.info(f"Initial owner {owner.email} claimed {updated} legacy entries")
        return updated
