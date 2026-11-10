import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import unquote
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.api.routes import entries as entry_routes
from app.models.schemas import SubtitleFormat
from app.services.subtitle_service import (
    MAX_CUE_CHARS,
    MAX_CUE_DURATION,
    MAX_LINE_CHARS,
    MIN_CUE_DURATION,
    SRT_ENCODING,
    build_cues,
    content_disposition,
    format_timestamp,
    subtitle_filenames,
    to_srt,
    wrap_lines,
)

try:  # Strict third-party parser, used as an independent format check.
    import srt as srt_lib
except ImportError:  # pragma: no cover - optional test dependency
    srt_lib = None


def seg(text, start, end):
    return {"text": text, "start": start, "end": end}


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


class FormatTimestampTests(TestCase):
    def test_zero(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")

    def test_rounds_to_millisecond_without_overflowing(self):
        self.assertEqual(format_timestamp(59.9996), "00:01:00,000")
        self.assertEqual(format_timestamp(1.2344), "00:00:01,234")
        self.assertEqual(format_timestamp(1.2346), "00:00:01,235")

    def test_hours(self):
        self.assertEqual(format_timestamp(3 * 3600 + 25 * 60 + 7.5), "03:25:07,500")

    def test_negative_is_clamped(self):
        self.assertEqual(format_timestamp(-2), "00:00:00,000")


class WrapLinesTests(TestCase):
    def test_short_text_is_one_line(self):
        self.assertEqual(wrap_lines("Hello there."), ["Hello there."])

    def test_long_text_is_balanced_over_two_lines(self):
        text = "This sentence is definitely longer than forty-two characters."
        lines = wrap_lines(text)
        self.assertEqual(len(lines), 2)
        self.assertEqual(" ".join(lines), text)
        self.assertTrue(all(len(line) <= MAX_LINE_CHARS for line in lines))


class BuildCuesTests(TestCase):
    def test_no_timestamps_gives_no_cues(self):
        self.assertEqual(build_cues(None, None), [])
        self.assertEqual(build_cues([], []), [])
        self.assertEqual(build_cues([{"text": "x"}], [{"word": "x"}]), [])

    def test_short_segments_map_one_to_one(self):
        cues = build_cues(
            [seg(" Hello world. ", 0.0, 1.5), seg("Second line.", 1.5, 3.0)],
            None,
        )
        self.assertEqual([c.text for c in cues], ["Hello world.", "Second line."])
        self.assertEqual((cues[0].start, cues[0].end), (0.0, 1.5))
        self.assertEqual((cues[1].start, cues[1].end), (1.5, 3.0))

    def test_segment_text_wins_over_unpunctuated_words(self):
        cues = build_cues(
            [seg("Hello, world.", 0.0, 1.5)],
            [word("hello", 0.0, 0.5), word("world", 0.6, 1.4)],
        )
        self.assertEqual(cues[0].text, "Hello, world.")

    def test_long_segment_is_split_using_word_timings(self):
        text_tokens = [f"word{i}" for i in range(30)]
        words = [word(t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(text_tokens)]
        cues = build_cues([seg(" ".join(text_tokens), 0.0, 15.0)], words)

        self.assertGreater(len(cues), 1)
        self.assertEqual(" ".join(c.text for c in cues), " ".join(text_tokens))
        self.assertEqual(cues[0].start, 0.0)
        self.assertEqual(cues[-1].end, 15.0)
        for cue in cues:
            self.assertLessEqual(len(cue.text), MAX_CUE_CHARS)
            self.assertLessEqual(
                cue.end - cue.start,
                MAX_CUE_DURATION + MIN_CUE_DURATION,
            )
        # Interior boundaries come from word timings, not interpolation.
        word_starts = {w["start"] for w in words}
        for cue in cues[1:]:
            self.assertIn(cue.start, word_starts)

    def test_long_segment_without_matching_words_is_interpolated(self):
        text = " ".join(["lorem"] * 40)
        cues = build_cues([seg(text, 10.0, 30.0)], None)
        self.assertGreater(len(cues), 1)
        self.assertEqual(cues[0].start, 10.0)
        self.assertEqual(cues[-1].end, 30.0)
        starts = [c.start for c in cues]
        self.assertEqual(starts, sorted(starts))
        # Interpolated cues are back to back, with no flicker gap between them.
        for previous, current in zip(cues, cues[1:]):
            self.assertAlmostEqual(previous.end, current.start)

    def test_splits_prefer_sentence_ends(self):
        text = (
            "The first sentence is right here. Then a second one follows it, "
            "and it keeps going for quite a while longer than allowed."
        )
        cues = build_cues([seg(text, 0.0, 12.0)], None)
        self.assertEqual(cues[0].text, "The first sentence is right here.")

    def test_words_only_are_grouped(self):
        words = [
            word("Hello", 0.0, 0.3),
            word("there.", 0.35, 0.7),
            word("After", 2.0, 2.3),
            word("pause", 2.35, 2.7),
        ]
        cues = build_cues(None, words)
        self.assertEqual([c.text for c in cues], ["Hello there.", "After pause"])

    def test_overlaps_are_trimmed_and_short_cues_extended(self):
        cues = build_cues(
            [seg("One.", 0.0, 0.2), seg("Two.", 0.5, 2.5), seg("Three.", 2.0, 4.0)],
            None,
        )
        self.assertEqual(cues[0].end, 0.5)  # extended, but only up to the next cue
        self.assertEqual(cues[1].end, 2.0)  # trimmed to the next start
        self.assertEqual(cues[2].end, 4.0)
        self.assertEqual(
            build_cues([seg("Hi.", 5.0, 5.1)], None)[0].end,
            5.0 + MIN_CUE_DURATION,
        )

    def test_cues_starting_together_keep_a_duration(self):
        cues = build_cues([seg("A.", 1.0, 2.0), seg("B.", 1.0, 3.0)], None)
        self.assertTrue(all(c.end > c.start for c in cues))

    def test_newlines_and_arrows_are_removed_from_text(self):
        cues = build_cues([seg("line one\n\nline --> two", 0.0, 2.0)], None)
        self.assertEqual(cues[0].text, "line one line -> two")

    def test_invalid_items_are_skipped(self):
        cues = build_cues(
            [
                "nope",
                seg("", 0, 1),
                seg("ok", float("nan"), 1),
                {"text": "bool", "start": True, "end": 2},
                seg("Kept.", 3.0, 4.0),
            ],
            None,
        )
        self.assertEqual([c.text for c in cues], ["Kept."])

    def test_unsorted_segments_are_ordered(self):
        cues = build_cues([seg("Later.", 5.0, 6.0), seg("Earlier.", 1.0, 2.0)], None)
        self.assertEqual([c.text for c in cues], ["Earlier.", "Later."])


class ToSrtTests(TestCase):
    def make_srt(self):
        segments = [
            seg("Grüß Gott, schön dass Sie da sind.", 0.0, 2.5),
            seg(
                "This sentence is definitely longer than forty-two characters.",
                2.5,
                6.0,
            ),
            seg("Final words after an hour.", 3600.0, 3602.25),
        ]
        return to_srt(build_cues(segments, None))

    def test_exact_layout(self):
        expected = (
            "1\r\n00:00:00,000 --> 00:00:02,500\r\nGrüß Gott, schön dass Sie da sind.\r\n"
            "\r\n"
            "2\r\n00:00:02,500 --> 00:00:06,000\r\n"
            "This sentence is definitely\r\nlonger than forty-two characters.\r\n"
            "\r\n"
            "3\r\n01:00:00,000 --> 01:00:02,250\r\nFinal words after an hour.\r\n"
        )
        self.assertEqual(self.make_srt(), expected)

    def test_empty(self):
        self.assertEqual(to_srt([]), "")

    def test_round_trips_through_strict_parser(self):
        if srt_lib is None:
            self.skipTest("srt package not installed")
        raw = self.make_srt().encode(SRT_ENCODING)
        parsed = list(srt_lib.parse(raw.decode(SRT_ENCODING), ignore_errors=False))
        self.assertEqual([p.index for p in parsed], [1, 2, 3])
        self.assertEqual(parsed[0].content, "Grüß Gott, schön dass Sie da sind.")
        self.assertEqual(parsed[2].start.total_seconds(), 3600.0)


class FilenameTests(TestCase):
    def entry(self, **kwargs):
        defaults = {"id": uuid4(), "filename": None, "title": ""}
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_uses_upload_filename_without_extension(self):
        ascii_name, unicode_name = subtitle_filenames(
            self.entry(filename="meeting 2026-11-03.mp3", title="Ignored"),
        )
        self.assertEqual(ascii_name, "transcript_meeting_2026-11-03.srt")
        self.assertEqual(unicode_name, "transcript_meeting 2026-11-03.srt")

    def test_falls_back_to_title(self):
        ascii_name, unicode_name = subtitle_filenames(
            self.entry(title="Größe/Übersicht: Q4"),
        )
        self.assertEqual(ascii_name, "transcript_Groesse_Uebersicht_Q4.srt")
        self.assertEqual(unicode_name, "transcript_Größe_Übersicht_ Q4.srt")

    def test_falls_back_to_entry_id(self):
        entry = self.entry(title="日本語")
        ascii_name, unicode_name = subtitle_filenames(entry)
        self.assertEqual(ascii_name, f"transcript_{str(entry.id)[:8]}.srt")
        self.assertEqual(unicode_name, "transcript_日本語.srt")

    def test_long_names_are_truncated(self):
        ascii_name, _ = subtitle_filenames(self.entry(title="a" * 300))
        self.assertEqual(len(ascii_name), len("transcript_.srt") + 100)

    def test_content_disposition_encodes_unicode_name(self):
        header = content_disposition("transcript_a.srt", "transcript_ä b.srt")
        self.assertTrue(header.startswith('attachment; filename="transcript_a.srt"; '))
        encoded = header.split("filename*=UTF-8''", 1)[1]
        self.assertNotIn(" ", encoded)
        self.assertEqual(unquote(encoded), "transcript_ä b.srt")


class SubtitleRouteTests(TestCase):
    def call(self, entry):
        with (
            patch.object(entry_routes, "_load_entry_or_404", return_value=entry),
            patch.object(
                entry_routes,
                "require_entry_access",
            ) as require_access,
        ):
            response = asyncio.run(
                entry_routes.download_entry_subtitles(
                    entry.id,
                    SubtitleFormat.SRT,
                    db=MagicMock(),
                    current_user=MagicMock(),
                ),
            )
        return response, require_access

    def make_entry(self, segments=None, words=None):
        return SimpleNamespace(
            id=uuid4(),
            title="Weekly sync",
            filename="weekly.m4a",
            transcript_segments=json.dumps(segments) if segments is not None else None,
            transcript_words=json.dumps(words) if words is not None else None,
        )

    def test_returns_srt_attachment(self):
        entry = self.make_entry(segments=[seg("Hallo zusammen.", 0.0, 1.5)])
        response, require_access = self.call(entry)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/x-subrip; charset=utf-8")
        self.assertIn(
            'filename="transcript_weekly.srt"',
            response.headers["content-disposition"],
        )
        self.assertTrue(response.body.startswith(b"\xef\xbb\xbf1\r\n"))
        self.assertIn(b"Hallo zusammen.", response.body)
        self.assertEqual(require_access.call_args.args[3].value, "view")

    def test_missing_timestamps_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.call(self.make_entry())
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Timestamps", ctx.exception.detail)
