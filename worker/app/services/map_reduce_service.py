import asyncio
from collections.abc import Awaitable, Callable, Sequence

from loguru import logger

from app.services.chunking_service import Chunk, estimate_tokens

# One LLM request: takes chat messages, returns the completion text.
LLMCall = Callable[[list[dict[str, str]]], Awaitable[str]]

# Max estimated tokens fed into a single reduce/merge call, leaving headroom
# for prompt overhead and output within a 128k-class context window.
REDUCE_INPUT_BUDGET = 100_000

PARTIAL_SEPARATOR = "\n\n---\n\n"


async def map_chunks(
    llm_call: LLMCall,
    chunks: Sequence[Chunk],
    build_messages: Callable[[Chunk], list[dict[str, str]]],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[str | None]:
    """Run every chunk through llm_call in parallel.

    Returns partials in chunk order. A chunk that still fails after one
    retry yields None — callers must surface the gap, never silently drop
    coverage. on_progress(done, total) fires after each chunk completes.
    """
    results: list[str | None] = [None] * len(chunks)
    done = 0

    async def run(i: int, chunk: Chunk) -> None:
        nonlocal done
        try:
            results[i] = await _call_with_retry(llm_call, build_messages(chunk))
        except Exception as e:
            logger.warning(f"Map call failed for chunk {chunk.index} after retry: {e}")
            results[i] = None
        done += 1
        if on_progress:
            await on_progress(done, len(chunks))

    await asyncio.gather(*(run(i, c) for i, c in enumerate(chunks)))
    return results


async def _call_with_retry(llm_call: LLMCall, messages: list[dict[str, str]]) -> str:
    try:
        return await llm_call(messages)
    except Exception:
        return await llm_call(messages)


async def collapse_partials(
    llm_call: LLMCall,
    partials: list[str],
    build_merge_messages: Callable[[str], list[dict[str, str]]],
    budget: int = REDUCE_INPUT_BUDGET,
) -> str:
    """Join partials, recursively merging batches while they exceed budget.

    Returns a single text that fits within `budget` (or a single partial,
    which cannot be split further), ready for the caller's final reduce
    prompt. Each pass shrinks the input, so this terminates.
    """
    depth = 0
    while True:
        joined = PARTIAL_SEPARATOR.join(partials)
        if len(partials) == 1 or estimate_tokens(joined) <= budget:
            if depth:
                logger.info(f"Recursive reduce finished at depth {depth}")
            return joined
        depth += 1
        batches = _batch_by_budget(partials, budget)
        partials = list(
            await asyncio.gather(
                *(
                    llm_call(build_merge_messages(PARTIAL_SEPARATOR.join(batch)))
                    for batch in batches
                ),
            ),
        )


def _batch_by_budget(partials: list[str], budget: int) -> list[list[str]]:
    """Greedy-pack partials into batches whose estimated size fits budget."""
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for partial in partials:
        tokens = estimate_tokens(partial)
        if current and size + tokens > budget:
            batches.append(current)
            current = []
            size = 0
        current.append(partial)
        size += tokens
    if current:
        batches.append(current)
    return batches
