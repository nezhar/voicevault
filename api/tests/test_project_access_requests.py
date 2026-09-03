import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.api.routes import projects as project_routes
from app.core.config import AuthMode
from app.models.project import AccessRequestStatus, ProjectRole
from app.models.schemas import (
    AccessRequestCreate,
    AccessRequestDecision,
    ProjectPreviewResponse,
)
from app.services.access_request_service import AlreadyMemberError


def make_user(user_id=None):
    return SimpleNamespace(id=user_id or uuid4(), email="me@corp", display_name="Me")


def make_project(project_id=None):
    return SimpleNamespace(id=project_id or uuid4(), name="Team Alpha")


class SchemaTests(TestCase):
    def test_decision_defaults_to_the_lowest_role(self):
        self.assertEqual(AccessRequestDecision().role, ProjectRole.VIEWER)

    def test_message_is_optional_and_length_capped(self):
        self.assertIsNone(AccessRequestCreate().message)
        with self.assertRaises(ValueError):
            AccessRequestCreate(message="x" * 501)

    def test_preview_allows_no_role_and_no_request(self):
        preview = ProjectPreviewResponse(
            id="11111111-1111-1111-1111-111111111111",
            name="Team Alpha",
            owners=[{"display_name": "Ada", "email": "ada@corp"}],
            can_request=True,
        )
        self.assertIsNone(preview.my_role)
        self.assertIsNone(preview.request_status)
        self.assertIsNone(preview.request_id)

    def test_preview_carries_request_state(self):
        preview = ProjectPreviewResponse(
            id="11111111-1111-1111-1111-111111111111",
            name="Team Alpha",
            owners=[],
            my_role=ProjectRole.VIEWER,
            request_status=AccessRequestStatus.PENDING,
            request_id="22222222-2222-2222-2222-222222222222",
            can_request=False,
        )
        self.assertEqual(preview.request_status, AccessRequestStatus.PENDING)


class PreviewRouteTests(IsolatedAsyncioTestCase):
    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_non_member_gets_name_owners_and_can_request(self, service_mock):
        project = make_project()
        service_mock.return_value.preview.return_value = {
            "project": project,
            "owners": [SimpleNamespace(display_name="Ada", email="ada@corp")],
            "role": None,
            "request": None,
        }

        result = await project_routes.preview_project(
            project.id,
            MagicMock(),
            make_user(),
        )

        self.assertEqual(result.name, "Team Alpha")
        self.assertEqual(result.owners[0].email, "ada@corp")
        self.assertIsNone(result.my_role)
        self.assertTrue(result.can_request)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_member_cannot_request(self, service_mock):
        project = make_project()
        service_mock.return_value.preview.return_value = {
            "project": project,
            "owners": [],
            "role": ProjectRole.VIEWER,
            "request": None,
        }

        result = await project_routes.preview_project(
            project.id,
            MagicMock(),
            make_user(),
        )

        self.assertEqual(result.my_role, ProjectRole.VIEWER)
        self.assertFalse(result.can_request)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.TOKEN)
    @patch.object(project_routes.settings, "access_token", "secret")
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_outside_oidc_preview_works_but_forbids_requesting(
        self,
        service_mock,
    ):
        project = make_project()
        service_mock.return_value.preview.return_value = {
            "project": project,
            "owners": [],
            "role": None,
            "request": None,
        }

        result = await project_routes.preview_project(
            project.id,
            MagicMock(),
            make_user(),
        )

        self.assertFalse(result.can_request)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_unknown_project_is_404(self, service_mock):
        service_mock.return_value.preview.side_effect = LookupError("gone")

        with self.assertRaises(HTTPException) as ctx:
            await project_routes.preview_project(uuid4(), MagicMock(), make_user())

        self.assertEqual(ctx.exception.status_code, 404)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_pending_request_is_reported_with_its_id(self, service_mock):
        project = make_project()
        request_id = uuid4()
        service_mock.return_value.preview.return_value = {
            "project": project,
            "owners": [],
            "role": None,
            "request": SimpleNamespace(
                id=request_id,
                status=AccessRequestStatus.PENDING,
            ),
        }

        result = await project_routes.preview_project(
            project.id,
            MagicMock(),
            make_user(),
        )

        self.assertEqual(result.request_status, AccessRequestStatus.PENDING)
        self.assertEqual(result.request_id, request_id)


class ListProjectsBadgeTests(IsolatedAsyncioTestCase):
    @patch("app.api.routes.projects.AccessRequestService")
    @patch("app.api.routes.projects.ProjectService")
    async def test_owner_projects_carry_pending_counts(
        self,
        project_service_mock,
        request_service_mock,
    ):
        owned = make_project()
        joined = make_project()
        for project in (owned, joined):
            project.description = None
            project.created_by = uuid4()
            project.created_at = "2026-01-01T00:00:00"
            project.updated_at = "2026-01-01T00:00:00"

        project_service_mock.return_value.list_for_user.return_value = [
            {
                "project": owned,
                "role": ProjectRole.OWNER,
                "member_count": 2,
                "entry_count": 3,
            },
            {
                "project": joined,
                "role": ProjectRole.VIEWER,
                "member_count": 5,
                "entry_count": 1,
            },
        ]
        request_service_mock.return_value.pending_counts.return_value = {owned.id: 4}

        result = await project_routes.list_projects(MagicMock(), make_user())

        self.assertEqual(result[0].pending_request_count, 4)
        self.assertEqual(result[1].pending_request_count, 0)
        request_service_mock.return_value.pending_counts.assert_called_once_with(
            [owned.id],
        )


def stored_request(user, status=AccessRequestStatus.PENDING):
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        user_id=user.id,
        user=user,
        status=status,
        message="let me in",
        created_at="2026-01-01T00:00:00",
        decided_at=None,
        decider=None,
    )


class RequestAccessRouteTests(IsolatedAsyncioTestCase):
    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    @patch("app.api.routes.projects.ProjectService")
    async def test_creates_a_request(self, project_service_mock, request_service_mock):
        user = make_user()
        project = make_project()
        project_service_mock.return_value.get_project.return_value = project
        request_service_mock.return_value.create_or_reopen.return_value = (
            stored_request(user)
        )

        result = await project_routes.request_access(
            project.id,
            AccessRequestCreate(message="let me in"),
            MagicMock(),
            user,
        )

        self.assertEqual(result.status, AccessRequestStatus.PENDING)
        self.assertEqual(result.message, "let me in")
        request_service_mock.return_value.create_or_reopen.assert_called_once_with(
            project,
            user,
            "let me in",
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    @patch("app.api.routes.projects.ProjectService")
    async def test_member_gets_409(self, project_service_mock, request_service_mock):
        project_service_mock.return_value.get_project.return_value = make_project()
        request_service_mock.return_value.create_or_reopen.side_effect = (
            AlreadyMemberError("already a member")
        )

        with self.assertRaises(HTTPException) as ctx:
            await project_routes.request_access(
                uuid4(),
                AccessRequestCreate(),
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 409)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.ProjectService")
    async def test_unknown_project_is_404(self, project_service_mock):
        project_service_mock.return_value.get_project.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await project_routes.request_access(
                uuid4(),
                AccessRequestCreate(),
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 404)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.TOKEN)
    @patch.object(project_routes.settings, "access_token", "secret")
    async def test_hidden_outside_oidc_mode(self):
        with self.assertRaises(HTTPException) as ctx:
            await project_routes.request_access(
                uuid4(),
                AccessRequestCreate(),
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 404)


class CancelRequestRouteTests(IsolatedAsyncioTestCase):
    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_cancels_own_request(self, request_service_mock):
        project_id, request_id = uuid4(), uuid4()
        user = make_user()

        result = await project_routes.cancel_access_request(
            project_id,
            request_id,
            MagicMock(),
            user,
        )

        self.assertEqual(result, {"message": "Access request cancelled"})
        request_service_mock.return_value.cancel.assert_called_once_with(
            project_id,
            request_id,
            user,
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_someone_elses_request_is_404(self, request_service_mock):
        request_service_mock.return_value.cancel.side_effect = LookupError("nope")

        with self.assertRaises(HTTPException) as ctx:
            await project_routes.cancel_access_request(
                uuid4(),
                uuid4(),
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 404)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_decided_request_is_409(self, request_service_mock):
        request_service_mock.return_value.cancel.side_effect = ValueError("decided")

        with self.assertRaises(HTTPException) as ctx:
            await project_routes.cancel_access_request(
                uuid4(),
                uuid4(),
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 409)


class OwnerDecisionRouteTests(IsolatedAsyncioTestCase):
    def _patch_owner_project(self, project):
        """_load_project_and_membership is the shared owner gate; stub it so
        these tests cover the decision logic, not authz (see test_authz.py)."""

        return patch.object(
            project_routes,
            "_load_project_and_membership",
            return_value=(
                MagicMock(),
                project,
                SimpleNamespace(role=ProjectRole.OWNER),
            ),
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_lists_pending_requests_by_default(self, request_service_mock):
        project = make_project()
        user = make_user()
        request_service_mock.return_value.list_for_project.return_value = [
            stored_request(user),
        ]

        with self._patch_owner_project(project):
            result = await project_routes.list_access_requests(
                project.id,
                "pending",
                MagicMock(),
                user,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].email, "me@corp")
        request_service_mock.return_value.list_for_project.assert_called_once_with(
            project,
            AccessRequestStatus.PENDING,
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_status_all_passes_none(self, request_service_mock):
        project = make_project()
        request_service_mock.return_value.list_for_project.return_value = []

        with self._patch_owner_project(project):
            await project_routes.list_access_requests(
                project.id,
                "all",
                MagicMock(),
                make_user(),
            )

        request_service_mock.return_value.list_for_project.assert_called_once_with(
            project,
            None,
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_approve_forwards_the_selected_role(self, request_service_mock):
        project = make_project()
        user = make_user()
        decided = stored_request(user, AccessRequestStatus.APPROVED)
        request_service_mock.return_value.approve.return_value = decided

        with self._patch_owner_project(project):
            result = await project_routes.approve_access_request(
                project.id,
                decided.id,
                AccessRequestDecision(role=ProjectRole.EDITOR),
                MagicMock(),
                user,
            )

        self.assertEqual(result.status, AccessRequestStatus.APPROVED)
        request_service_mock.return_value.approve.assert_called_once_with(
            project,
            decided.id,
            user,
            ProjectRole.EDITOR,
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_approve_defaults_to_viewer(self, request_service_mock):
        project = make_project()
        user = make_user()
        decided = stored_request(user, AccessRequestStatus.APPROVED)
        request_service_mock.return_value.approve.return_value = decided

        with self._patch_owner_project(project):
            await project_routes.approve_access_request(
                project.id,
                decided.id,
                AccessRequestDecision(),
                MagicMock(),
                user,
            )

        self.assertEqual(
            request_service_mock.return_value.approve.call_args.args[3],
            ProjectRole.VIEWER,
        )

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_deny_marks_the_request(self, request_service_mock):
        project = make_project()
        user = make_user()
        decided = stored_request(user, AccessRequestStatus.DENIED)
        request_service_mock.return_value.deny.return_value = decided

        with self._patch_owner_project(project):
            result = await project_routes.deny_access_request(
                project.id,
                decided.id,
                MagicMock(),
                user,
            )

        self.assertEqual(result.status, AccessRequestStatus.DENIED)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.projects.AccessRequestService")
    async def test_unknown_request_is_404(self, request_service_mock):
        project = make_project()
        request_service_mock.return_value.approve.side_effect = LookupError("gone")

        with self._patch_owner_project(project):
            with self.assertRaises(HTTPException) as ctx:
                await project_routes.approve_access_request(
                    project.id,
                    uuid4(),
                    AccessRequestDecision(),
                    MagicMock(),
                    make_user(),
                )

        self.assertEqual(ctx.exception.status_code, 404)

    @patch.object(project_routes.settings, "auth_mode", AuthMode.TOKEN)
    @patch.object(project_routes.settings, "access_token", "secret")
    async def test_listing_is_hidden_outside_oidc_mode(self):
        with self.assertRaises(HTTPException) as ctx:
            await project_routes.list_access_requests(
                uuid4(),
                "pending",
                MagicMock(),
                make_user(),
            )

        self.assertEqual(ctx.exception.status_code, 404)
