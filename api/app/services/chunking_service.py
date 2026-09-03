import re
from dataclasses import dataclass

# Provider-agnostic token estimate: ~4 characters per token.
CHARS_PER_TOKEN = 4

# End-of-sentence punctuation, optionally followed by closing quotes/brackets,
# then whitespace.
_SENTENCE_END = re.compile(r'[.!?]["\')\]]*\s')


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start_char: int
    end_char: int


def estimate_tokens(text: str) -> int:
    """Approximate token count (chars / 4). Provider-agnostic by design."""
    return len(text) // CHARS_PER_TOKEN


def split_transcript(text: str, split_size: int, overlap: int) -> list[Chunk]:
    """Split text into overlapping chunks of at most ~split_size tokens.

    Cuts on sentence boundaries when possible, falling back to word
    boundaries, then hard cuts. Deterministic: the same input and settings
    always produce the same chunks. start/end positions refer to the
    original text; chunks are never persisted.
    """
    if not text or not text.strip():
        return []

    target_chars = split_size * CHARS_PER_TOKEN
    overlap_chars = overlap * CHARS_PER_TOKEN

    if len(text) <= target_chars:
        return [Chunk(index=0, text=text, start_char=0, end_char=len(text))]

    chunks: list[Chunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + target_chars, len(text))
        if end < len(text):
            end = start + _last_boundary(text[start:end])
        chunks.append(
            Chunk(index=index, text=text[start:end], start_char=start, end_char=end),
        )
        if end >= len(text):
            break
        index += 1
        # Next chunk re-reads the last `overlap` tokens; always move forward.
        start = max(end - overlap_chars, start + 1)
    return chunks


def _last_boundary(window: str) -> int:
    """Best cut position in window: after the last sentence end, else after
    the last space, else the full window (hard cut)."""
    last = None
    for match in _SENTENCE_END.finditer(window):
        last = match.end()
    if last:
        return last
    space = window.rfind(" ")
    if space > 0:
        return space + 1
    return len(window)
