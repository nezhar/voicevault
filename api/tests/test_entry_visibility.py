import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.entry_service import EntryService


class GetEntriesSignatureTests(TestCase):
    def _user(self):
        return SimpleNamespace(id=uuid4())

    def test_applies_visibility_filter(self):
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.count.return_value = 0
        query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        entries, total = EntryService(db).get_entries(user=self._user())

        self.assertEqual((entries, total), ([], 0))
        # base archived filter + visibility filter = at least 2 filter calls
        self.assertGreaterEqual(query.filter.call_count, 2)

    def test_owner_only_and_private_only_add_filters(self):
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.count.return_value = 0
        query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        EntryService(db).get_entries(
            user=self._user(),
            owner_only=True,
            private_only=True,
        )

        self.assertGreaterEqual(query.filter.call_count, 4)


class SetEntryProjectTests(TestCase):
    def test_updates_project_and_commits(self):
        db = MagicMock()
        entry = SimpleNamespace(id=uuid4(), project_id=None)
        target = uuid4()

        result = EntryService(db).set_entry_project(entry, target)

        self.assertEqual(entry.project_id, target)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(entry)
        self.assertIs(result, entry)
