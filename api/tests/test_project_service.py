import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.entry import Entry
from app.models.project import ProjectRole
from app.services.project_service import LastOwnerError, ProjectService


def owner_member(user_id=None):
    return SimpleNamespace(user_id=user_id or uuid4(), role=ProjectRole.OWNER)


class CreateProjectTests(TestCase):
    def test_creator_becomes_owner(self):
        db = MagicMock()
        creator = SimpleNamespace(id=uuid4())

        ProjectService(db).create_project("Team", None, creator)

        added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
        self.assertIn("Project", added_types)
        self.assertIn("ProjectMember", added_types)
        member = next(
            call.args[0]
            for call in db.add.call_args_list
            if type(call.args[0]).__name__ == "ProjectMember"
        )
        self.assertEqual(member.role, ProjectRole.OWNER)
        self.assertEqual(member.user_id, creator.id)
        db.commit.assert_called_once()


class AddMemberTests(TestCase):
    @patch("app.services.project_service.UserService")
    def test_unknown_email_raises_lookup_error(self, user_service_mock):
        user_service_mock.return_value.get_by_email.return_value = None
        db = MagicMock()
        project = SimpleNamespace(id=uuid4())

        with self.assertRaises(LookupError):
            ProjectService(db).add_member(project, "ghost@corp", ProjectRole.VIEWER)

    @patch("app.services.project_service.UserService")
    def test_duplicate_member_raises_value_error(self, user_service_mock):
        member_user = SimpleNamespace(id=uuid4())
        user_service_mock.return_value.get_by_email.return_value = member_user
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = owner_member(
            member_user.id,
        )
        project = SimpleNamespace(id=uuid4())

        with self.assertRaises(ValueError):
            ProjectService(db).add_member(project, "dup@corp", ProjectRole.VIEWER)


class LastOwnerProtectionTests(TestCase):
    def _service_with_single_owner(self, member):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = member
        # count of OTHER owners in the project
        db.query.return_value.filter.return_value.count.return_value = 0
        return ProjectService(db)

    def test_cannot_demote_last_owner(self):
        member = owner_member()
        service = self._service_with_single_owner(member)
        project = SimpleNamespace(id=uuid4())

        with self.assertRaises(LastOwnerError):
            service.update_member_role(project, member.user_id, ProjectRole.EDITOR)

    def test_cannot_remove_last_owner(self):
        member = owner_member()
        service = self._service_with_single_owner(member)
        project = SimpleNamespace(id=uuid4())

        with self.assertRaises(LastOwnerError):
            service.remove_member(project, member.user_id)


class DeleteProjectTests(TestCase):
    def test_detaches_entries_before_deleting(self):
        db = MagicMock()
        project = SimpleNamespace(id=uuid4())
        calls = []
        db.query.return_value.filter.return_value.update.side_effect = (
            lambda *a, **k: calls.append("detach")
        )
        db.delete.side_effect = lambda obj: calls.append("delete")

        ProjectService(db).delete_project(project)

        # entries must be detached explicitly (no FK on upgraded databases),
        # and before the project row goes away
        db.query.return_value.filter.return_value.update.assert_called_once_with(
            {Entry.project_id: None},
            synchronize_session=False,
        )
        self.assertEqual(calls, ["detach", "delete"])
        db.delete.assert_called_once_with(project)
        db.commit.assert_called_once()
