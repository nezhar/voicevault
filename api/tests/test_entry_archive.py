import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.entry import EntryStatus
from app.services.entry_service import EntryService


class EntryServiceArchiveTests(TestCase):
    def make_entry(self, *, status=EntryStatus.READY, archived=False):
        return SimpleNamespace(
            id=uuid4(),
            status=status,
            archived=archived,
        )

    def test_archives_ready_entries(self):
        db = MagicMock()
        service = EntryService(db)
        entry = self.make_entry()
        service.get_entry = MagicMock(return_value=entry)

        result = service.set_entry_archived(entry.id, True)

        self.assertIs(result, entry)
        self.assertTrue(entry.archived)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(entry)

    def test_rejects_archiving_non_ready_entries(self):
        db = MagicMock()
        service = EntryService(db)
        entry = self.make_entry(status=EntryStatus.IN_PROGRESS)
        service.get_entry = MagicMock(return_value=entry)

        with self.assertRaisesRegex(ValueError, "Only READY entries can be archived"):
            service.set_entry_archived(entry.id, True)

        self.assertFalse(entry.archived)
        db.commit.assert_not_called()
        db.refresh.assert_not_called()

    def test_unarchives_entries(self):
        db = MagicMock()
        service = EntryService(db)
        entry = self.make_entry(archived=True)
        service.get_entry = MagicMock(return_value=entry)

        result = service.set_entry_archived(entry.id, False)

        self.assertIs(result, entry)
        self.assertFalse(entry.archived)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(entry)
