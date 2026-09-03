import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.chunking_service import split_transcript


class WorkerChunkingSmokeTests(TestCase):
    def test_split_produces_overlapping_coverage(self):
        text = " ".join(
            f"Sentence number {i} talks about topic {i}." for i in range(200)
        )
        chunks = split_transcript(text, 100, 10)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[-1].end_char, len(text))
