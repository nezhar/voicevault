"""Derive consumption metrics from stored transcript data.

Pure functions only — no database, no S3 — so they can be reused by the ASR
worker at write time and by the backfill script, and unit-tested directly.
"""

import json
from typing import Any


def parse_json_list(raw: str | None) -> list[Any] | None:
    """Decode a JSON array column, tolerating NULL and malformed values."""

    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, list) else None


def duration_from_segments(segments: list[dict[str, Any]] | None) -> float | None:
    """Audio duration, taken as the latest segment end time.

    Whisper emits segments spanning the whole audio, so the maximum end is the
    duration to within a fraction of a second. Segments are not assumed to be
    ordered.
    """

    if not segments:
        return None

    ends = [
        segment["end"]
        for segment in segments
        if isinstance(segment, dict)
        and isinstance(segment.get("end"), (int, float))
        and not isinstance(segment.get("end"), bool)
    ]
    if not ends:
        return None
    return float(max(ends))


def count_words(
    transcript: str | None,
    words: list[Any] | None,
) -> int | None:
    """Word count, preferring the ASR word list over splitting the transcript."""

    if words:
        return len(words)
    if transcript and transcript.strip():
        return len(transcript.split())
    return None
