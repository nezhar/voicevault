import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.project import AccessRequestStatus, ProjectAccessRequest, ProjectRole
from app.services import access_request_service as service_module
from app.services.access_request_service import (
    AccessRequestService,
    AlreadyMemberError,
)


def make_user(user_id=None):
    return SimpleNamespace(id=user_id or uuid4())


def make_project(project_id=None):
    return SimpleNamespace(id=project_id or uuid4(), name="Team Alpha")


def existing_request(user_id, status=AccessRequestStatus.PENDING):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        message=None,
        decided_by=uuid4(),
        decided_at="2026-01-01",
    )


class ModelShapeTests(TestCase):
    def test_table_name_and_unique_constraint(self):
        self.assertEqual(ProjectAccessRequest.__tablename__, "project_access_requests")
        constraint_columns = {
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in ProjectAccessRequest.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("project_id", "user_id"), constraint_columns)

    def test_status_values(self):
        self.assertEqual(AccessRequestStatus.PENDING, "pending")
        self.assertEqual(AccessRequestStatus.APPROVED, "approved")
        self.assertEqual(AccessRequestStatus.DENIED, "denied")

    def test_new_request_defaults_to_pending(self):
        column = ProjectAccessRequest.__table__.columns["status"]
        self.assertEqual(column.default.arg, AccessRequestStatus.PENDING)
        self.assertFalse(column.nullable)


class CreateRequestTests(TestCase):
    @patch.object(service_module, "get_membership", return_value=None)
    def test_first_request_is_added_as_pending(self, _membership):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = make_user()
        project = make_project()

        request = AccessRequestService(db).create_or_reopen(project, user, "let me in")

        self.assertIsInstance(request, ProjectAccessRequest)
        self.assertEqual(request.project_id, project.id)
        self.assertEqual(request.user_id, user.id)
        self.assertEqual(request.message, "let me in")
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @patch.object(service_module, "get_membership", return_value=None)
    def test_denied_request_reopens_the_same_row(self, _membership):
        user = make_user()
        stored = existing_request(user.id, AccessRequestStatus.DENIED)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        request = AccessRequestService(db).create_or_reopen(
            make_project(),
            user,
            "trying again",
        )

        self.assertIs(request, stored)
        self.assertEqual(request.status, AccessRequestStatus.PENDING)
        self.assertEqual(request.message, "trying again")
        self.assertIsNone(request.decided_by)
        self.assertIsNone(request.decided_at)
        db.add.assert_not_called()
        db.commit.assert_called_once()

    @patch.object(
        service_module,
        "get_membership",
        return_value=SimpleNamespace(role=ProjectRole.VIEWER),
    )
    def test_member_cannot_request_access(self, _membership):
        db = MagicMock()

        with self.assertRaises(AlreadyMemberError):
            AccessRequestService(db).create_or_reopen(make_project(), make_user(), None)

        db.commit.assert_not_called()


class CancelRequestTests(TestCase):
    def test_requester_cancels_own_pending_request(self):
        user = make_user()
        stored = existing_request(user.id)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored
        project = make_project()

        AccessRequestService(db).cancel(project.id, stored.id, user)

        db.delete.assert_called_once_with(stored)
        db.commit.assert_called_once()

    def test_cannot_cancel_someone_elses_request(self):
        stored = existing_request(uuid4())
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        with self.assertRaises(LookupError):
            AccessRequestService(db).cancel(uuid4(), stored.id, make_user())

        db.delete.assert_not_called()

    def test_cannot_cancel_a_decided_request(self):
        user = make_user()
        stored = existing_request(user.id, AccessRequestStatus.APPROVED)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        with self.assertRaises(ValueError):
            AccessRequestService(db).cancel(uuid4(), stored.id, user)

        db.delete.assert_not_called()


class ApproveTests(TestCase):
    @patch.object(service_module, "get_membership", return_value=None)
    def test_approve_creates_member_with_selected_role(self, _membership):
        requester_id = uuid4()
        stored = existing_request(requester_id)
        stored.status = AccessRequestStatus.PENDING
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored
        project = make_project()
        decider = make_user()

        request = AccessRequestService(db).approve(
            project,
            stored.id,
            decider,
            ProjectRole.EDITOR,
        )

        member = db.add.call_args.args[0]
        self.assertEqual(type(member).__name__, "ProjectMember")
        self.assertEqual(member.project_id, project.id)
        self.assertEqual(member.user_id, requester_id)
        self.assertEqual(member.role, ProjectRole.EDITOR)
        self.assertEqual(request.status, AccessRequestStatus.APPROVED)
        self.assertEqual(request.decided_by, decider.id)
        self.assertIsNotNone(request.decided_at)
        db.commit.assert_called_once()

    @patch.object(
        service_module,
        "get_membership",
        return_value=SimpleNamespace(role=ProjectRole.VIEWER),
    )
    def test_approve_does_not_duplicate_an_existing_member(self, _membership):
        stored = existing_request(uuid4())
        stored.status = AccessRequestStatus.PENDING
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        request = AccessRequestService(db).approve(
            make_project(),
            stored.id,
            make_user(),
            ProjectRole.VIEWER,
        )

        db.add.assert_not_called()
        self.assertEqual(request.status, AccessRequestStatus.APPROVED)

    @patch.object(service_module, "get_membership", return_value=None)
    def test_approving_twice_is_a_no_op(self, _membership):
        stored = existing_request(uuid4(), AccessRequestStatus.APPROVED)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        request = AccessRequestService(db).approve(
            make_project(),
            stored.id,
            make_user(),
            ProjectRole.OWNER,
        )

        self.assertEqual(request.status, AccessRequestStatus.APPROVED)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_unknown_request_raises_lookup_error(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with self.assertRaises(LookupError):
            AccessRequestService(db).approve(
                make_project(),
                uuid4(),
                make_user(),
                ProjectRole.VIEWER,
            )


class DenyTests(TestCase):
    def test_deny_keeps_the_row_and_records_the_decider(self):
        stored = existing_request(uuid4())
        stored.status = AccessRequestStatus.PENDING
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored
        decider = make_user()

        request = AccessRequestService(db).deny(make_project(), stored.id, decider)

        self.assertEqual(request.status, AccessRequestStatus.DENIED)
        self.assertEqual(request.decided_by, decider.id)
        self.assertIsNotNone(request.decided_at)
        db.delete.assert_not_called()
        db.commit.assert_called_once()

    def test_denying_twice_is_a_no_op(self):
        stored = existing_request(uuid4(), AccessRequestStatus.DENIED)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = stored

        AccessRequestService(db).deny(make_project(), stored.id, make_user())

        db.commit.assert_not_called()


class ListRequestsTests(TestCase):
    def test_defaults_to_pending_only(self):
        db = MagicMock()
        chain = db.query.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.all.return_value = ["row"]

        result = AccessRequestService(db).list_for_project(make_project())

        self.assertEqual(result, ["row"])
        chain.filter.assert_called_once()

    def test_status_none_returns_every_request(self):
        db = MagicMock()
        chain = db.query.return_value.filter.return_value
        chain.order_by.return_value.all.return_value = ["a", "b"]

        result = AccessRequestService(db).list_for_project(make_project(), status=None)

        self.assertEqual(result, ["a", "b"])
        chain.filter.assert_not_called()


class PreviewTests(TestCase):
    def _db_with(self, project, owners, request):
        """query(Project) -> project, query(ProjectMember) -> owners,
        query(ProjectAccessRequest) -> request."""

        db = MagicMock()

        def query(model):
            result = MagicMock()
            name = getattr(model, "__name__", "")
            if name == "Project":
                result.filter.return_value.first.return_value = project
            elif name == "ProjectMember":
                result.filter.return_value.all.return_value = owners
            else:
                result.filter.return_value.first.return_value = request
            return result

        db.query.side_effect = query
        return db

    @patch.object(service_module, "get_membership", return_value=None)
    def test_non_member_sees_project_and_owners(self, _membership):
        project = make_project()
        owner_user = SimpleNamespace(display_name="Ada", email="ada@corp")
        owners = [SimpleNamespace(user=owner_user)]
        db = self._db_with(project, owners, None)

        preview = AccessRequestService(db).preview(project.id, make_user())

        self.assertIs(preview["project"], project)
        self.assertEqual(preview["owners"], [owner_user])
        self.assertIsNone(preview["role"])
        self.assertIsNone(preview["request"])

    @patch.object(
        service_module,
        "get_membership",
        return_value=SimpleNamespace(role=ProjectRole.EDITOR),
    )
    def test_member_preview_reports_their_role(self, _membership):
        project = make_project()
        db = self._db_with(project, [], None)

        preview = AccessRequestService(db).preview(project.id, make_user())

        self.assertEqual(preview["role"], ProjectRole.EDITOR)

    def test_unknown_project_raises_lookup_error(self):
        db = self._db_with(None, [], None)

        with self.assertRaises(LookupError):
            AccessRequestService(db).preview(uuid4(), make_user())


class PendingCountTests(TestCase):
    def test_empty_input_skips_the_query(self):
        db = MagicMock()

        self.assertEqual(AccessRequestService(db).pending_counts([]), {})

        db.query.assert_not_called()

    def test_groups_counts_by_project(self):
        first, second = uuid4(), uuid4()
        db = MagicMock()
        chain = db.query.return_value.filter.return_value.group_by.return_value
        chain.all.return_value = [(first, 2), (second, 1)]

        counts = AccessRequestService(db).pending_counts([first, second])

        self.assertEqual(counts, {first: 2, second: 1})
