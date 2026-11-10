"""Build SubRip (.srt) subtitles from stored ASR timestamps.

Whisper segments carry the punctuated, cased text, while the word list (Groq
in particular) usually has no punctuation. Segment text is therefore the source
of truth; words are only used to time the split points when a segment is too
long for a single subtitle cue. Entries without segments fall back to grouping
the word stream directly.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from collections.abc import Iterable
from urllib.parse import quote

# Common subtitle conventions: two lines of ~42 characters, a cue on screen
# for at most ~7 seconds and long enough to be read.
MAX_LINE_CHARS = 42
MAX_CUE_CHARS = MAX_LINE_CHARS * 2
MAX_CUE_DURATION = 7.0
MIN_CUE_DURATION = 1.0
# Same pause threshold the audio player modal uses to break transcript lines.
PAUSE_BREAK_SECONDS = 0.6
# Break after sentence/clause punctuation once a cue has this much text, so
# cues end at natural boundaries instead of only at the hard length limit.
MIN_CHARS_FOR_SENTENCE_BREAK = 15
MIN_CHARS_FOR_CLAUSE_BREAK = MAX_LINE_CHARS
# Words are matched to a segment when they fall inside it, with some slack
# for rounding at the boundaries.
SEGMENT_MATCH_SLACK = 0.05

SENTENCE_END = re.compile(r"[.!?…][\"')\]»“”]*$")
CLAUSE_END = re.compile(r"[,;:–—][\"')\]»“”]*$")

SRT_MEDIA_TYPE = "application/x-subrip"
# UTF-8 with BOM: Windows players and smart TVs otherwise tend to read the
# file as cp1252, garbling umlauts. VLC, mpv, ffmpeg and YouTube accept it.
SRT_ENCODING = "utf-8-sig"
SRT_NEWLINE = "\r\n"

MAX_FILENAME_STEM = 100
_GERMAN_TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"},
)


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class _Token:
    text: str
    start: float
    end: float


def _as_time(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _clean_text(text: str) -> str:
    # A blank line terminates an SRT cue and "-->" is the timing separator, so
    # neither may survive inside cue text.
    return " ".join(text.replace("-->", "->").split())


def _normalize(items: list[Any] | None, text_key: str) -> list[_Token]:
    result: list[_Token] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        text = item.get(text_key)
        start = _as_time(item.get("start"))
        end = _as_time(item.get("end"))
        if not isinstance(text, str) or start is None or end is None:
            continue
        text = _clean_text(text)
        if not text:
            continue
        start = max(start, 0.0)
        result.append(_Token(text=text, start=start, end=max(end, start)))
    result.sort(key=lambda t: (t.start, t.end))
    return result


def _proportional_token_times(
    text_tokens: list[str],
    start: float,
    end: float,
) -> list[_Token]:
    """Spread a segment's duration over its tokens by character position.

    Each token owns its trailing space, so consecutive tokens - and therefore
    the cues built from them - are contiguous instead of flickering apart.
    """

    total = sum(len(t) for t in text_tokens) + len(text_tokens) - 1
    duration = end - start
    tokens: list[_Token] = []
    pos = 0
    for index, text in enumerate(text_tokens):
        token_start = start + duration * pos / total
        pos += len(text) + (1 if index < len(text_tokens) - 1 else 0)
        token_end = start + duration * pos / total
        tokens.append(_Token(text=text, start=token_start, end=token_end))
    return tokens


def _segment_tokens(segment: _Token, words: list[_Token]) -> list[_Token]:
    text_tokens = segment.text.split()
    matched = [
        w
        for w in words
        if w.start >= segment.start - SEGMENT_MATCH_SLACK
        and w.end <= segment.end + SEGMENT_MATCH_SLACK
    ]
    if matched and len(matched) == len(text_tokens):
        # Word timings with the segment's punctuated text, clamped into the
        # segment so cue boundaries never escape it.
        return [
            _Token(
                text=text,
                start=min(max(w.start, segment.start), segment.end),
                end=min(max(w.end, segment.start), segment.end),
            )
            for text, w in zip(text_tokens, matched)
        ]
    return _proportional_token_times(text_tokens, segment.start, segment.end)


def _chunk_tokens(tokens: list[_Token]) -> list[Cue]:
    cues: list[Cue] = []
    current: list[_Token] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            cues.append(
                Cue(
                    start=current[0].start,
                    end=current[-1].end,
                    text=" ".join(t.text for t in current),
                ),
            )
        current = []
        current_len = 0

    for token in tokens:
        if current:
            too_long = current_len + 1 + len(token.text) > MAX_CUE_CHARS
            too_slow = token.end - current[0].start > MAX_CUE_DURATION
            paused = token.start - current[-1].end >= PAUSE_BREAK_SECONDS
            if too_long or too_slow or paused:
                flush()
        current.append(token)
        current_len += len(token.text) + (1 if current_len else 0)
        if (
            SENTENCE_END.search(token.text)
            and current_len >= MIN_CHARS_FOR_SENTENCE_BREAK
        ) or (
            CLAUSE_END.search(token.text) and current_len >= MIN_CHARS_FOR_CLAUSE_BREAK
        ):
            flush()
    flush()
    return cues


def _split_segment(segment: _Token, words: list[_Token]) -> list[Cue]:
    if (
        len(segment.text) <= MAX_CUE_CHARS
        and segment.end - segment.start <= MAX_CUE_DURATION
    ):
        return [Cue(start=segment.start, end=segment.end, text=segment.text)]
    cues = _chunk_tokens(_segment_tokens(segment, words))
    if cues:
        # The segment's own bounds are more reliable than interpolated or
        # word-level ones at its edges.
        cues[0].start = segment.start
        cues[-1].end = max(cues[-1].end, segment.end)
    return cues


def _finalize(cues: list[Cue]) -> list[Cue]:
    cues = sorted((c for c in cues if c.text), key=lambda c: (c.start, c.end))
    for index, cue in enumerate(cues):
        next_start = cues[index + 1].start if index + 1 < len(cues) else math.inf
        end = max(cue.end, cue.start + MIN_CUE_DURATION)
        # Trim into the next cue's start, unless both start together - then a
        # brief overlap beats a zero-length cue that players would skip.
        if min(end, next_start) > cue.start:
            end = min(end, next_start)
        cue.end = end
    return cues


def build_cues(
    segments: list[Any] | None,
    words: list[Any] | None,
) -> list[Cue]:
    """Subtitle cues for a transcript; empty when no timestamps are stored."""

    normalized_segments = _normalize(segments, "text")
    normalized_words = _normalize(words, "word")
    if normalized_segments:
        cues: list[Cue] = []
        for segment in normalized_segments:
            cues.extend(_split_segment(segment, normalized_words))
    else:
        cues = _chunk_tokens(normalized_words)
    return _finalize(cues)


def wrap_lines(text: str, max_line: int = MAX_LINE_CHARS) -> list[str]:
    """Split cue text into at most two lines, breaking near the middle."""

    if len(text) <= max_line:
        return [text]
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return [text]
    split = min(
        spaces,
        key=lambda i: (max(i, len(text) - i - 1), abs(len(text) / 2 - i)),
    )
    return [text[:split], text[split + 1 :]]


def format_timestamp(seconds: float) -> str:
    """SRT timestamp HH:MM:SS,mmm, rounded to the millisecond."""

    total_ms = round(max(seconds, 0.0) * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(cues: Iterable[Cue]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        lines = [
            str(index),
            f"{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}",
            *wrap_lines(cue.text),
        ]
        blocks.append(SRT_NEWLINE.join(lines) + SRT_NEWLINE)
    return SRT_NEWLINE.join(blocks)


def _filename_stem(entry: Any) -> str:
    filename = (getattr(entry, "filename", None) or "").strip()
    if filename:
        stem = filename.rsplit(".", 1)[0] if "." in filename[1:] else filename
    else:
        stem = (getattr(entry, "title", None) or "").strip()
    return stem


def subtitle_filenames(entry: Any, extension: str = "srt") -> tuple[str, str]:
    """(ASCII fallback, UTF-8) download names: ``transcript_<stem>.<ext>``.

    The stem is the uploaded filename without its extension, else the title.
    """

    stem = _filename_stem(entry)
    unicode_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]+', "_", stem)
    unicode_stem = re.sub(r"\s+", " ", unicode_stem).strip(" ._")[:MAX_FILENAME_STEM]

    ascii_stem = unicodedata.normalize("NFKD", stem.translate(_GERMAN_TRANSLITERATION))
    ascii_stem = ascii_stem.encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem)
    ascii_stem = re.sub(r"_+", "_", ascii_stem).strip("._-")[:MAX_FILENAME_STEM]

    fallback = str(getattr(entry, "id", "") or "")[:8] or "export"
    ascii_name = f"transcript_{ascii_stem or fallback}.{extension}"
    unicode_name = f"transcript_{unicode_stem or ascii_stem or fallback}.{extension}"
    return ascii_name, unicode_name


def content_disposition(ascii_name: str, unicode_name: str) -> str:
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(unicode_name, safe='')}"
    )
