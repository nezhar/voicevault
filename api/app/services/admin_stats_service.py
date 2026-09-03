"""Read-only aggregation behind /api/admin.

The SQL lives in one place and stays deliberately thin; everything that can be
reasoned about without a database — the sort whitelist and the row-to-schema
mapping — is a pure function so it can be unit-tested. This repo has no
database-backed test fixture, so that split is what keeps the module honest.
"""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import is_admin_user
from app.core.timeutils import utcnow
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.project import Project, ProjectMember
from app.models.schemas import (
    AdminSystemStatsResponse,
    AdminUserListResponse,
    AdminUserStatsResponse,
)
from app.models.user import User

# Aggregate expressions are defined once and reused by both the SELECT list and
# ORDER BY, so a sort can never disagree with the column it claims to sort.
ENTRY_COUNT = func.count(Entry.id)
STORAGE_BYTES = func.coalesce(func.sum(Entry.file_size_bytes), 0)
DURATION_SECONDS = func.coalesce(func.sum(Entry.duration_seconds), 0.0)
WORD_COUNT = func.coalesce(func.sum(Entry.word_count), 0)

SORT_EXPRESSIONS = {
    "entry_count": ENTRY_COUNT,
    "storage_bytes": STORAGE_BYTES,
    "duration_seconds": DURATION_SECONDS,
    "word_count": WORD_COUNT,
    "email": User.email,
    "created_at": User.created_at,
}

DEFAULT_SORT = "storage_bytes"


def resolve_sort(sort: str, order: str):
    """Map a request's sort parameters onto a SQLAlchemy expression.

    Names are looked up in a whitelist and never interpolated into SQL.
    """

    expression = SORT_EXPRESSIONS.get(sort)
    if expression is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sort field. Allowed: {', '.join(sorted(SORT_EXPRESSIONS))}",
        )
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")

    return expression.desc() if order == "desc" else expression.asc()


def build_system_stats(
    *,
    users_total: int,
    users_active_30d: int,
    users_new_30d: int,
    entry_totals,
    status_rows,
    source_rows,
    projects_total: int,
) -> AdminSystemStatsResponse:
    """Assemble the system response, zero-filling buckets the query omitted."""

    by_status = {status.value: 0 for status in EntryStatus}
    for name, count in status_rows:
        key = name.value if hasattr(name, "value") else str(name)
        by_status[key] = count

    by_source = {source.value: 0 for source in SourceType}
    for name, count in source_rows:
        key = name.value if hasattr(name, "value") else str(name)
        by_source[key] = count

    return AdminSystemStatsResponse(
        users_total=users_total,
        users_active_30d=users_active_30d,
        users_new_30d=users_new_30d,
        entries_total=entry_totals.entries_total or 0,
        entries_archived=entry_totals.entries_archived or 0,
        entries_by_status=by_status,
        entries_by_source=by_source,
        storage_bytes_total=int(entry_totals.storage_bytes_total or 0),
        duration_seconds_total=float(entry_totals.duration_seconds_total or 0.0),
        words_total=int(entry_totals.words_total or 0),
        projects_total=projects_total,
        entries_missing_metrics=entry_totals.entries_missing_metrics or 0,
        entries_unassigned=entry_totals.entries_unassigned or 0,
    )


def build_user_stats(rows) -> list[AdminUserStatsResponse]:
    """Map aggregate rows onto the response schema."""

    return [
        AdminUserStatsResponse(
            id=row.user_id,
            email=row.email,
            display_name=row.display_name,
            is_admin=is_admin_user(row),
            is_system=bool(row.is_system),
            created_at=row.created_at,
            last_login_at=row.last_login_at,
            entry_count=row.entry_count or 0,
            storage_bytes=int(row.storage_bytes or 0),
            duration_seconds=float(row.duration_seconds or 0.0),
            word_count=int(row.word_count or 0),
            error_count=row.error_count or 0,
            project_count=row.project_count or 0,
        )
        for row in rows
    ]


class AdminStatsService:
    """Aggregates platform-wide consumption. Read-only by construction."""

    def __init__(self, db: Session):
        self.db = db

    # -- system ---------------------------------------------------------

    def system_stats(self) -> AdminSystemStatsResponse:
        cutoff = utcnow() - timedelta(days=30)
        real_users = User.is_system.is_(False)

        users_total = self.db.query(func.count(User.id)).filter(real_users).scalar()
        users_active_30d = (
            self.db.query(func.count(User.id))
            .filter(real_users, User.last_login_at >= cutoff)
            .scalar()
        )
        users_new_30d = (
            self.db.query(func.count(User.id))
            .filter(real_users, User.created_at >= cutoff)
            .scalar()
        )

        # An entry counts as "missing metrics" when its size is unknown, or when
        # it finished transcribing without recording duration or words. A NEW
        # entry with no duration is normal and must not raise a false alarm.
        missing = or_(
            Entry.file_size_bytes.is_(None),
            (Entry.status == EntryStatus.READY)
            & (Entry.duration_seconds.is_(None) | Entry.word_count.is_(None)),
        )

        entry_totals = self.db.query(
            func.count(Entry.id).label("entries_total"),
            func.coalesce(func.sum(Entry.file_size_bytes), 0).label(
                "storage_bytes_total",
            ),
            func.coalesce(func.sum(Entry.duration_seconds), 0.0).label(
                "duration_seconds_total",
            ),
            func.coalesce(func.sum(Entry.word_count), 0).label("words_total"),
            func.count(case((Entry.archived.is_(True), 1))).label("entries_archived"),
            func.count(case((missing, 1))).label("entries_missing_metrics"),
            # Orphan entries (user_id IS NULL) are counted here but belong to no
            # User row, so the per-user table can never account for them. They
            # are surfaced rather than hidden: in OIDC mode legacy entries are
            # only claimed when INITIAL_OWNER_EMAIL is set, and app/main.py warns
            # they may stay unclaimed forever.
            func.count(case((Entry.user_id.is_(None), 1))).label("entries_unassigned"),
        ).one()

        status_rows = (
            self.db.query(Entry.status, func.count(Entry.id))
            .group_by(Entry.status)
            .all()
        )
        source_rows = (
            self.db.query(Entry.source_type, func.count(Entry.id))
            .group_by(Entry.source_type)
            .all()
        )
        projects_total = self.db.query(func.count(Project.id)).scalar()

        return build_system_stats(
            users_total=users_total or 0,
            users_active_30d=users_active_30d or 0,
            users_new_30d=users_new_30d or 0,
            entry_totals=entry_totals,
            status_rows=status_rows,
            source_rows=source_rows,
            projects_total=projects_total or 0,
        )

    # -- per user -------------------------------------------------------

    def _user_scope(self):
        """Real users, plus the system user only while it still owns entries.

        Dropping a system user that owns entries would make the per-user table
        disagree with entries_total; dropping an empty one keeps a synthetic
        account from being counted as a person.

        Callers MUST outer-join Entry (``.outerjoin(Entry, Entry.user_id ==
        User.id)``) before applying this predicate. It references ``Entry.id``,
        so without that join SQLAlchemy adds Entry to the FROM list on its own
        and the result is a silent cartesian product — every system user looks
        like an owner and the counts inflate without any error.
        """

        return or_(User.is_system.is_(False), Entry.id.isnot(None))

    def user_stats(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        sort: str = DEFAULT_SORT,
        order: str = "desc",
    ) -> AdminUserListResponse:
        ordering = resolve_sort(sort, order)

        project_counts = (
            select(
                ProjectMember.user_id.label("user_id"),
                func.count(ProjectMember.project_id).label("project_count"),
            )
            .group_by(ProjectMember.user_id)
            .subquery()
        )

        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.email.label("email"),
                User.display_name.label("display_name"),
                User.is_system.label("is_system"),
                User.created_at.label("created_at"),
                User.last_login_at.label("last_login_at"),
                ENTRY_COUNT.label("entry_count"),
                STORAGE_BYTES.label("storage_bytes"),
                DURATION_SECONDS.label("duration_seconds"),
                WORD_COUNT.label("word_count"),
                func.count(case((Entry.status == EntryStatus.ERROR, 1))).label(
                    "error_count",
                ),
                func.coalesce(project_counts.c.project_count, 0).label("project_count"),
            )
            .outerjoin(Entry, Entry.user_id == User.id)
            .outerjoin(project_counts, project_counts.c.user_id == User.id)
            .filter(self._user_scope())
            .group_by(User.id, project_counts.c.project_count)
            # User.id is a tiebreaker, not decoration: the default sort is
            # storage_bytes desc and most users tie at 0 (same for entry_count
            # and word_count). PostgreSQL guarantees no order among ties, so
            # without a unique second key successive OFFSET pages could repeat
            # some users and skip others entirely.
            .order_by(ordering, User.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

        # `total` counts the rows this list can page through, which is a
        # different population from AdminSystemStatsResponse.users_total: that
        # one counts people (real users only), this one adds the system user
        # while it still owns entries. So total == users_total + 1 is expected,
        # not a bug — do not "reconcile" them, and do not render one where the
        # other belongs.
        total = (
            self.db.query(func.count(func.distinct(User.id)))
            .select_from(User)
            .outerjoin(Entry, Entry.user_id == User.id)
            .filter(self._user_scope())
            .scalar()
        )

        return AdminUserListResponse(
            total=total or 0,
            users=build_user_stats(rows),
        )
