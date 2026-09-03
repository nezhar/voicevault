import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.entry_metrics import (
    count_words,
    duration_from_segments,
    parse_json_list,
)


class DurationFromSegmentsTests(TestCase):
    def test_uses_the_latest_segment_end(self):
        segments = [
            {"text": "hello", "start": 0.0, "end": 3.5},
            {"text": "world", "start": 3.5, "end": 12.25},
        ]

        self.assertEqual(duration_from_segments(segments), 12.25)

    def test_unordered_segments_still_yield_the_maximum(self):
        segments = [
            {"text": "b", "start": 9.0, "end": 20.0},
            {"text": "a", "start": 0.0, "end": 5.0},
        ]

        self.assertEqual(duration_from_segments(segments), 20.0)

    def test_returns_none_for_empty_or_missing_input(self):
        self.assertIsNone(duration_from_segments(None))
        self.assertIsNone(duration_from_segments([]))

    def test_ignores_segments_without_a_numeric_end(self):
        segments = [
            {"text": "a", "end": None},
            {"text": "b"},
            {"text": "c", "end": 4.0},
        ]

        self.assertEqual(duration_from_segments(segments), 4.0)

    def test_returns_none_when_no_segment_has_a_usable_end(self):
        self.assertIsNone(duration_from_segments([{"text": "a"}, {"text": "b"}]))

    def test_ignores_a_boolean_end(self):
        # isinstance(True, int) is True, so without the explicit bool guard this
        # would report a bogus one-second duration.
        self.assertIsNone(duration_from_segments([{"end": True}]))

    def test_ignores_entries_that_are_not_dicts(self):
        self.assertEqual(duration_from_segments(["not a dict", {"end": 4.0}]), 4.0)


class CountWordsTests(TestCase):
    def test_prefers_the_word_timestamp_list(self):
        words = [{"word": "one"}, {"word": "two"}, {"word": "three"}]

        self.assertEqual(count_words("one two", words), 3)

    def test_falls_back_to_whitespace_split_transcript(self):
        self.assertEqual(count_words("one two  three\nfour", None), 4)

    def test_falls_back_to_the_transcript_when_the_word_list_is_empty(self):
        # The whisper-asr-webservice fallback returns no word list and
        # parse_json_list("[]") yields [], so an empty list must not be taken
        # as a zero word count — this is what `if words:` buys over
        # `if words is not None:`.
        self.assertEqual(count_words("one two", []), 2)

    def test_returns_none_without_any_usable_input(self):
        self.assertIsNone(count_words(None, None))
        self.assertIsNone(count_words("   ", []))


class ParseJsonListTests(TestCase):
    def test_parses_a_json_array(self):
        self.assertEqual(parse_json_list('[{"end": 1.0}]'), [{"end": 1.0}])

    def test_returns_none_for_empty_malformed_or_non_list_json(self):
        self.assertIsNone(parse_json_list(None))
        self.assertIsNone(parse_json_list(""))
        self.assertIsNone(parse_json_list("not json"))
        self.assertIsNone(parse_json_list('{"end": 1.0}'))
