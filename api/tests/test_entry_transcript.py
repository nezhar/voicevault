import sys
from pathlib import Path

from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.entry import EntryStatus, SourceType
from app.services.entry_service import EntryService


class EntryServiceTranscriptTests(TestCase):
    def test_creates_ready_entry_from_existing_transcript(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        service = EntryService(db)

        entry = service.create_transcript_entry(
            title="Board sync",
            transcript="Already transcribed content",
        )

        self.assertEqual(entry.title, "Board sync")
        self.assertEqual(entry.source_type, SourceType.UPLOAD)
        self.assertEqual(entry.status, EntryStatus.READY)
        self.assertEqual(entry.transcript, "Already transcribed content")
        db.add.assert_called_once_with(entry)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(entry)
