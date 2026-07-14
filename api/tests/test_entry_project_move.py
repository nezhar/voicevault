import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.api.routes import entries as entries_routes
from app.models.project import ProjectRole


class MoveEntryToProjectTests(IsolatedAsyncioTestCase):
    """Route-level authorization wiring for PUT /entries/{id}/project.

    Runs the real route function and the real authz logic; only the
    membership lookup and entry loading touch fakes instead of a database.
    """

    def setUp(self):
        self.owner = SimpleNamespace(id=uuid4())
        self.other = SimpleNamespace(id=uuid4())
        self.source_project = uuid4()
        self.target_project = uuid4()
        self.entry = SimpleNamespace(
            id=uuid4(),
            user_id=self.owner.id,
            project_id=None,
        )
        # (project_id, user_id) -> ProjectMember-like
        self.memberships = {}

        def fake_membership(db, project_id, user_id):
            return self.memberships.get((project_id, user_id))

        patchers = [
            # entries.py holds its own imported reference; authz uses its own
            patch.object(entries_routes, "get_membership", fake_membership),
            patch("app.services.authz.get_membership", fake_membership),
            patch.object(entries_routes, "EntryService"),
            patch.object(entries_routes, "EntryResponse"),
        ]
        mocks = [p.start() for p in patchers]
        for p in patchers:
            self.addCleanup(p.stop)

        self.entry_service = mocks[2].return_value
        self.entry_service.get_entry.return_value = self.entry
        self.entry_service.set_entry_project.side_effect = lambda entry, pid: entry

    def _grant(self, project_id, user, role):
        self.memberships[(project_id, user.id)] = SimpleNamespace(
            user_id=user.id,
            role=role,
        )

    async def _move(self, user, project_id):
        return await entries_routes.move_entry_to_project(
            self.entry.id,
            SimpleNamespace(project_id=project_id),
            db=MagicMock(),
            current_user=user,
        )

    async def test_owner_with_editor_role_moves_entry_into_project(self):
        self._grant(self.target_project, self.owner, ProjectRole.EDITOR)

        await self._move(self.owner, self.target_project)

        self.entry_service.set_entry_project.assert_called_once_with(
            self.entry,
            self.target_project,
        )

    async def test_owner_with_viewer_role_in_target_gets_403(self):
        self._grant(self.target_project, self.owner, ProjectRole.VIEWER)

        with self.assertRaises(HTTPException) as ctx:
            await self._move(self.owner, self.target_project)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_owner_not_member_of_target_gets_404(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._move(self.owner, self.target_project)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_project_member_who_is_not_entry_owner_cannot_move(self):
        # even a project owner may not move someone else's entry elsewhere
        self.entry.project_id = self.source_project
        self._grant(self.source_project, self.other, ProjectRole.OWNER)
        self._grant(self.target_project, self.other, ProjectRole.EDITOR)

        with self.assertRaises(HTTPException) as ctx:
            await self._move(self.other, self.target_project)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_stranger_gets_404_not_403(self):
        self.entry.project_id = self.source_project

        with self.assertRaises(HTTPException) as ctx:
            await self._move(self.other, self.target_project)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_entry_owner_removes_entry_from_project(self):
        self.entry.project_id = self.source_project

        await self._move(self.owner, None)

        self.entry_service.set_entry_project.assert_called_once_with(
            self.entry,
            None,
        )

    async def test_project_editor_removes_foreign_entry_from_project(self):
        self.entry.project_id = self.source_project
        self._grant(self.source_project, self.other, ProjectRole.EDITOR)

        await self._move(self.other, None)

        self.entry_service.set_entry_project.assert_called_once_with(
            self.entry,
            None,
        )

    async def test_project_viewer_cannot_remove_foreign_entry(self):
        self.entry.project_id = self.source_project
        self._grant(self.source_project, self.other, ProjectRole.VIEWER)

        with self.assertRaises(HTTPException) as ctx:
            await self._move(self.other, None)
        self.assertEqual(ctx.exception.status_code, 403)
