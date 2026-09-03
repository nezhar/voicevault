import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.chunking_service import (
    CHARS_PER_TOKEN,
    Chunk,
    estimate_tokens,
    split_transcript,
)


def make_text(sentences: int) -> str:
    return " ".join(
        f"Sentence number {i} talks about topic {i}." for i in range(sentences)
    )


class EstimateTokensTests(TestCase):
    def test_four_chars_per_token(self):
        self.assertEqual(estimate_tokens("a" * 40), 10)

    def test_empty(self):
        self.assertEqual(estimate_tokens(""), 0)


class SplitTranscriptTests(TestCase):
    def test_empty_text_returns_no_chunks(self):
        self.assertEqual(split_transcript("", 100, 10), [])
        self.assertEqual(split_transcript("   \n  ", 100, 10), [])

    def test_short_text_single_chunk(self):
        text = "One short sentence."
        chunks = split_transcript(text, 100, 10)
        self.assertEqual(
            chunks,
            [Chunk(index=0, text=text, start_char=0, end_char=len(text))],
        )

    def test_long_text_covers_everything_with_overlap(self):
        text = make_text(200)
        split_size, overlap = 100, 10
        chunks = split_transcript(text, split_size, overlap)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[-1].end_char, len(text))
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.index, i)
            self.assertEqual(chunk.text, text[chunk.start_char : chunk.end_char])
            # No chunk exceeds the target size
            self.assertLessEqual(len(chunk.text), split_size * CHARS_PER_TOKEN)
        for prev, nxt in zip(chunks, chunks[1:]):
            # Overlapping: next chunk starts before previous ends, but advances
            self.assertLess(nxt.start_char, prev.end_char)
            self.assertGreater(nxt.start_char, prev.start_char)

    def test_deterministic(self):
        text = make_text(150)
        self.assertEqual(split_transcript(text, 80, 8), split_transcript(text, 80, 8))

    def test_prefers_sentence_boundaries(self):
        text = make_text(200)
        chunks = split_transcript(text, 100, 10)
        # Every non-final chunk should end right after sentence punctuation
        for chunk in chunks[:-1]:
            self.assertTrue(chunk.text.rstrip().endswith("."), repr(chunk.text[-20:]))

    def test_no_punctuation_still_terminates(self):
        text = "word " * 2000  # no sentence punctuation at all
        chunks = split_transcript(text, 50, 5)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[-1].end_char, len(text))
