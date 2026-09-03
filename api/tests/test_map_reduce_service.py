import asyncio
import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.chunking_service import Chunk
from app.services.map_reduce_service import (
    PARTIAL_SEPARATOR,
    collapse_partials,
    map_chunks,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def chunk(i: int, text: str) -> Chunk:
    return Chunk(index=i, text=text, start_char=0, end_char=len(text))


class MapChunksTests(TestCase):
    def test_results_in_chunk_order(self):
        async def llm(messages):
            # Reverse-ordered delays: later chunks finish first
            n = int(messages[0]["content"])
            await asyncio.sleep(0.02 * (3 - n))
            return f"partial-{n}"

        chunks = [chunk(i, str(i)) for i in range(3)]
        results = run(
            map_chunks(llm, chunks, lambda c: [{"role": "user", "content": c.text}]),
        )
        self.assertEqual(results, ["partial-0", "partial-1", "partial-2"])

    def test_progress_called_per_completion(self):
        events = []

        async def llm(messages):
            return "ok"

        async def on_progress(done, total):
            events.append((done, total))

        chunks = [chunk(i, "x") for i in range(4)]
        run(map_chunks(llm, chunks, lambda c: [], on_progress))
        self.assertEqual(sorted(events), [(1, 4), (2, 4), (3, 4), (4, 4)])

    def test_failed_chunk_retries_once_then_none(self):
        calls = {"n": 0}

        async def llm(messages):
            calls["n"] += 1
            raise RuntimeError("boom")

        results = run(map_chunks(llm, [chunk(0, "x")], lambda c: []))
        self.assertEqual(results, [None])
        self.assertEqual(calls["n"], 2)  # original + one retry

    def test_retry_recovers(self):
        calls = {"n": 0}

        async def llm(messages):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return "recovered"

        results = run(map_chunks(llm, [chunk(0, "x")], lambda c: []))
        self.assertEqual(results, ["recovered"])


class CollapsePartialsTests(TestCase):
    def test_under_budget_joins_without_llm(self):
        async def llm(messages):
            raise AssertionError("must not be called")

        result = run(collapse_partials(llm, ["a", "b"], lambda t: [], budget=1000))
        self.assertEqual(result, f"a{PARTIAL_SEPARATOR}b")

    def test_over_budget_merges_recursively(self):
        merged = []

        async def llm(messages):
            merged.append(messages[0]["content"])
            return "m"  # tiny merge result

        partials = ["x" * 400, "y" * 400, "z" * 400]  # ~100 tokens each
        result = run(
            collapse_partials(
                llm,
                partials,
                lambda text: [{"role": "user", "content": text}],
                budget=150,
            ),
        )
        self.assertGreater(len(merged), 0)  # merge calls happened
        self.assertIn("m", result)

    def test_single_oversized_partial_terminates(self):
        async def llm(messages):
            raise AssertionError("must not be called for a single partial")

        result = run(collapse_partials(llm, ["x" * 4000], lambda t: [], budget=10))
        self.assertEqual(result, "x" * 4000)
