"""Effective capabilities: who may use which feature, globally or per project.

A user's capabilities are the union of their own grants, the grants of every
group they belong to and those of the built-in Everyone group. A project grant
only adds, and only for project-scoped capabilities. Admins hold everything. A
token holds what its owner holds, cut down to the token's own capabilities and
projects - so taking a capability from a user takes it from their tokens on the
next request.
"""

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException, Request
from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.capabilities import (
    ALL_CAPABILITIES,
    CATALOG,
    DEFAULT_EVERYONE,
    PROJECT_SCOPED,
    Capability,
    is_legacy,
    normalize_token_capabilities,
)
from app.models.capability_grant import CapabilityGrant
from app.models.group import EVERYONE_GROUP_NAME, Group, GroupMember
from app.models.personal_access_token import PersonalAccessToken
from app.models.project import Project
from app.models.user import User


@dataclass(frozen=True)
class Effective:
    global_caps: frozenset = frozenset()
    # Extra capabilities per project, on top of global_caps.
    project_caps: dict = field(default_factory=dict)
    # Token restriction: only these projects (personal entries excluded).
    project_filter: frozenset | None = None

    def has(self, cap: Capability, project_id: UUID | None = None) -> bool:
        cap = Capability(cap)
        if cap not in PROJECT_SCOPED:
            return cap in self.global_caps
        if self.project_filter is not None and project_id not in self.project_filter:
            return False
        if cap in self.global_caps:
            return True
        return project_id is not None and cap in self.project_caps.get(
            project_id,
            frozenset(),
        )

    def projects_with(self, cap: Capability) -> set | None:
        """Projects where cap holds; None means every project (and personal)."""

        cap = Capability(cap)
        if cap in self.global_caps and self.project_filter is None:
            return None
        if cap in self.global_caps:
            return set(self.project_filter)
        projects = {pid for pid, caps in self.project_caps.items() if cap in caps}
        if self.project_filter is not None:
            projects &= self.project_filter
        return projects

    def includes_personal(self, cap: Capability) -> bool:
        return self.project_filter is None and Capability(cap) in self.global_caps

    def anywhere(self, cap: Capability) -> bool:
        projects = self.projects_with(cap)
        return projects is None or bool(projects) or self.has(cap)


FULL = Effective(global_caps=frozenset(ALL_CAPABILITIES))


@dataclass(frozen=True)
class GrantSpec:
    capability: Capability
    project_id: UUID | None = None


class GrantError(ValueError):
    pass


class PermissionService:
    def __init__(self, db: Session):
        self.db = db

    # -- groups -----------------------------------------------------------

    def everyone(self) -> Group:
        group = self.db.query(Group).filter(Group.is_builtin.is_(True)).first()
        if group is None:
            group = Group(
                name=EVERYONE_GROUP_NAME,
                description="Every user. Its grants are the baseline for everybody.",
                is_builtin=True,
            )
            self.db.add(group)
            self.db.flush()
        return group

    def group_ids_for(self, user_id: UUID) -> list[UUID]:
        ids = [
            row[0]
            for row in self.db.query(GroupMember.group_id)
            .filter(GroupMember.user_id == user_id)
            .distinct()
            .all()
        ]
        everyone = self.db.query(Group.id).filter(Group.is_builtin.is_(True)).first()
        if everyone is not None:
            ids.append(everyone[0])
        return ids

    def _has_everyone(self) -> bool:
        return (
            self.db.query(Group.id).filter(Group.is_builtin.is_(True)).first()
            is not None
        )

    # -- evaluation -------------------------------------------------------

    def effective(self, user: User) -> Effective:
        from app.core.auth import is_admin_user

        if is_admin_user(user):
            return FULL
        group_ids = self.group_ids_for(user.id)
        subject = CapabilityGrant.user_id == user.id
        if group_ids:
            subject = or_(subject, CapabilityGrant.group_id.in_(group_ids))
        rows = (
            self.db.query(CapabilityGrant.capability, CapabilityGrant.project_id)
            .filter(subject)
            .all()
        )
        # Before seed_defaults has created Everyone (a database the API has not
        # started against yet), everybody keeps the pre-capability behaviour.
        global_caps: set[Capability] = (
            set() if self._has_everyone() else set(DEFAULT_EVERYONE)
        )
        per_project: dict[UUID, set[Capability]] = {}
        for name, project_id in rows:
            try:
                cap = Capability(name)
            except ValueError:
                continue  # a capability removed from the catalog
            if project_id is None:
                global_caps.add(cap)
            elif cap in PROJECT_SCOPED:
                per_project.setdefault(project_id, set()).add(cap)
        return Effective(
            global_caps=frozenset(global_caps),
            project_caps={
                pid: frozenset(caps - global_caps)
                for pid, caps in per_project.items()
                if caps - global_caps
            },
        )

    @staticmethod
    def for_token(owner: Effective, pat: PersonalAccessToken) -> Effective:
        allowed = token_capabilities(pat)
        project_filter = None
        project_ids = getattr(pat, "project_ids", None)
        if project_ids is not None:
            project_filter = frozenset(UUID(str(pid)) for pid in project_ids)
        return Effective(
            global_caps=frozenset(owner.global_caps & allowed),
            project_caps={
                pid: frozenset(caps & allowed)
                for pid, caps in owner.project_caps.items()
                if caps & allowed
            },
            project_filter=project_filter,
        )

    def explain(self, user: User) -> list[dict]:
        """Every grant that applies to the user, with where it comes from."""

        from app.core.auth import is_admin_user

        if is_admin_user(user):
            return [
                {"capability": cap.value, "project_id": None, "source": "admin"}
                for cap in sorted(ALL_CAPABILITIES, key=lambda c: c.value)
            ]
        group_ids = self.group_ids_for(user.id)
        groups = (
            {
                group.id: group.name
                for group in self.db.query(Group).filter(Group.id.in_(group_ids)).all()
            }
            if group_ids
            else {}
        )
        subject = CapabilityGrant.user_id == user.id
        if group_ids:
            subject = or_(subject, CapabilityGrant.group_id.in_(group_ids))
        result = []
        for grant in self.db.query(CapabilityGrant).filter(subject).all():
            result.append(
                {
                    "capability": grant.capability,
                    "project_id": grant.project_id,
                    "source": "user" if grant.user_id else groups.get(grant.group_id),
                },
            )
        result.sort(key=lambda r: (r["capability"], str(r["project_id"] or "")))
        return result

    # -- grants -----------------------------------------------------------

    def grants_for(
        self,
        *,
        user_id: UUID | None = None,
        group_id: UUID | None = None,
    ) -> list[CapabilityGrant]:
        query = self.db.query(CapabilityGrant)
        if user_id is not None:
            query = query.filter(CapabilityGrant.user_id == user_id)
        else:
            query = query.filter(CapabilityGrant.group_id == group_id)
        return query.order_by(CapabilityGrant.capability).all()

    def replace_grants(
        self,
        *,
        grants: list[GrantSpec],
        actor: User | None,
        user_id: UUID | None = None,
        group_id: UUID | None = None,
    ) -> list[CapabilityGrant]:
        if (user_id is None) == (group_id is None):
            raise GrantError("Name exactly one of user_id or group_id")
        wanted: set[tuple[Capability, UUID | None]] = set()
        for spec in grants:
            cap = Capability(spec.capability)
            if spec.project_id is not None:
                if cap not in PROJECT_SCOPED:
                    raise GrantError(f"{cap.value} can only be granted globally")
                if self.db.get(Project, spec.project_id) is None:
                    raise GrantError(f"Unknown project: {spec.project_id}")
            wanted.add((cap, spec.project_id))

        query = self.db.query(CapabilityGrant)
        if user_id is not None:
            query = query.filter(CapabilityGrant.user_id == user_id)
        else:
            query = query.filter(CapabilityGrant.group_id == group_id)
        existing = {}
        for grant in query.all():
            key = (grant.capability, grant.project_id)
            if (
                key in existing
                or (Capability(grant.capability), grant.project_id) not in wanted
            ):
                self.db.delete(grant)
            else:
                existing[key] = grant
        for cap, project_id in wanted:
            if (cap.value, project_id) not in existing:
                self.db.add(
                    CapabilityGrant(
                        user_id=user_id,
                        group_id=group_id,
                        capability=cap.value,
                        project_id=project_id,
                        granted_by=actor.id if actor is not None else None,
                    ),
                )
        self.db.commit()
        return self.grants_for(user_id=user_id, group_id=group_id)

    # -- startup ----------------------------------------------------------

    def seed_defaults(self) -> bool:
        """Create Everyone with today's behaviour on first run. Idempotent: an
        existing Everyone keeps whatever an admin has made of it."""

        existing = self.db.query(Group).filter(Group.is_builtin.is_(True)).first()
        if existing is not None:
            return False
        group = self.everyone()
        for cap in sorted(DEFAULT_EVERYONE, key=lambda c: c.value):
            self.db.add(CapabilityGrant(group_id=group.id, capability=cap.value))
        self.db.commit()
        logger.info("Created the Everyone group with the default capabilities")
        return True

    def convert_legacy_tokens(self) -> int:
        converted = 0
        for pat in self.db.query(PersonalAccessToken).all():
            values = list(pat.permissions or [])
            if not is_legacy(values):
                continue
            pat.permissions = normalize_token_capabilities(values)
            converted += 1
        if converted:
            self.db.commit()
            logger.info(f"Converted {converted} token(s) to capability names")
        return converted


# -- request helpers ------------------------------------------------------


def token_capabilities(pat) -> set[Capability]:
    """A token's capabilities; old scope names count as their replacements, so a
    token is usable before the startup conversion has rewritten it."""

    values = [v for v in (pat.permissions or []) if isinstance(v, str)]
    try:
        names = normalize_token_capabilities(values)
    except ValueError:
        names = []
        for value in values:
            try:
                names.extend(normalize_token_capabilities([value]))
            except ValueError:
                continue
    return {Capability(name) for name in names}


def current_effective(request: Request, db: Session, user: User) -> Effective:
    cached = getattr(request.state, "effective", None)
    if cached is not None and getattr(request.state, "effective_user", None) == user.id:
        return cached
    service = PermissionService(db)
    effective = service.effective(user)
    pat = getattr(request.state, "pat", None)
    if pat is not None:
        effective = service.for_token(effective, pat)
    request.state.effective = effective
    request.state.effective_user = user.id
    return effective


def _project_label(db: Session, project_id: UUID) -> str:
    project = db.get(Project, project_id)
    return f'project "{project.name}"' if project else "this project"


def require_capability(
    request: Request,
    db: Session,
    user: User,
    cap: Capability,
    project_id: UUID | None = None,
) -> Effective:
    effective = current_effective(request, db, user)
    if effective.has(cap, project_id):
        return effective
    cap = Capability(cap)
    if cap in PROJECT_SCOPED and project_id is not None:
        where = f"in {_project_label(db, project_id)}"
    elif cap in PROJECT_SCOPED and effective.project_filter is not None:
        where = "outside the projects this token is limited to"
    else:
        where = "globally"
    logger.warning(
        "authorization_denied user_id={} capability={} project_id={} method={} path={}",
        user.id,
        cap.value,
        project_id,
        request.method,
        request.url.path,
    )
    raise HTTPException(
        status_code=403,
        detail=f"Missing capability {cap.value} ({CATALOG[cap].label}) {where}",
    )


def capability_snapshot(effective: Effective) -> tuple[list[str], dict[str, list[str]]]:
    """What /api/auth/me reports: global capabilities and per-project extras."""

    global_caps = sorted(cap.value for cap in effective.global_caps)
    project_caps = {
        str(pid): sorted(cap.value for cap in caps)
        for pid, caps in effective.project_caps.items()
        if effective.project_filter is None or pid in effective.project_filter
    }
    if effective.project_filter is not None:
        # A project-limited token: global project-scoped capabilities hold only
        # inside its projects, so report them there instead of globally.
        scoped = sorted(
            cap.value for cap in effective.global_caps if cap in PROJECT_SCOPED
        )
        for pid in effective.project_filter:
            merged = set(project_caps.get(str(pid), [])) | set(scoped)
            if merged:
                project_caps[str(pid)] = sorted(merged)
        global_caps = sorted(
            cap.value for cap in effective.global_caps if cap not in PROJECT_SCOPED
        )
    return global_caps, project_caps
