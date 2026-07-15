import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.models.project import ProjectRole
from app.services import authz
from app.services.authz import AccessLevel, require_entry_access, require_project_role


def make_user():
    return SimpleNamespace(id=uuid4())


def make_entry(owner_id=None, project_id=None):
    return SimpleNamespace(id=uuid4(), user_id=owner_id, project_id=project_id)


def membership(role):
    return SimpleNamespace(role=role)


class EntryAccessTests(TestCase):
    def test_owner_has_every_level_on_private_entry(self):
        user = make_user()
        entry = make_entry(owner_id=user.id)
        for level in (AccessLevel.VIEW, AccessLevel.EDIT, AccessLevel.OWNER):
            require_entry_access(MagicMock(), entry, user, level)  # must not raise

    def test_stranger_gets_404_not_403(self):
        user = make_user()
        entry = make_entry(owner_id=uuid4())
        with patch.object(authz, "get_membership", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                require_entry_access(MagicMock(), entry, user, AccessLevel.VIEW)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_viewer_can_view_but_not_edit(self):
        user = make_user()
        entry = make_entry(owner_id=uuid4(), project_id=uuid4())
        with patch.object(
            authz,
            "get_membership",
            return_value=membership(ProjectRole.VIEWER),
        ):
            require_entry_access(MagicMock(), entry, user, AccessLevel.VIEW)
            with self.assertRaises(HTTPException) as ctx:
                require_entry_access(MagicMock(), entry, user, AccessLevel.EDIT)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_editor_can_edit_but_not_delete(self):
        user = make_user()
        entry = make_entry(owner_id=uuid4(), project_id=uuid4())
        with patch.object(
            authz,
            "get_membership",
            return_value=membership(ProjectRole.EDITOR),
        ):
            require_entry_access(MagicMock(), entry, user, AccessLevel.EDIT)
            with self.assertRaises(HTTPException) as ctx:
                require_entry_access(MagicMock(), entry, user, AccessLevel.OWNER)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_project_owner_still_cannot_delete_foreign_entry(self):
        user = make_user()
        entry = make_entry(owner_id=uuid4(), project_id=uuid4())
        with patch.object(
            authz,
            "get_membership",
            return_value=membership(ProjectRole.OWNER),
        ):
            with self.assertRaises(HTTPException) as ctx:
                require_entry_access(MagicMock(), entry, user, AccessLevel.OWNER)
        self.assertEqual(ctx.exception.status_code, 403)


class ProjectRoleTests(TestCase):
    def test_non_member_gets_404(self):
        project = SimpleNamespace(id=uuid4())
        with patch.object(authz, "get_membership", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                require_project_role(
                    MagicMock(),
                    project,
                    make_user(),
                    ProjectRole.VIEWER,
                )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_editor_is_not_enough_for_owner_actions(self):
        project = SimpleNamespace(id=uuid4())
        with patch.object(
            authz,
            "get_membership",
            return_value=membership(ProjectRole.EDITOR),
        ):
            with self.assertRaises(HTTPException) as ctx:
                require_project_role(
                    MagicMock(),
                    project,
                    make_user(),
                    ProjectRole.OWNER,
                )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_passes_and_membership_is_returned(self):
        project = SimpleNamespace(id=uuid4())
        owner_membership = membership(ProjectRole.OWNER)
        with patch.object(authz, "get_membership", return_value=owner_membership):
            result = require_project_role(
                MagicMock(),
                project,
                make_user(),
                ProjectRole.OWNER,
            )
        self.assertIs(result, owner_membership)
