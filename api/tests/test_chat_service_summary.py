import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_service(responses):
    """Build a ChatService with a mocked LLM client.

    responses: list of strings returned by successive completion calls
    (the last entry repeats once exhausted).
    """
    from app.services.chat_service import ChatService

    service = ChatService.__new__(ChatService)
    service.provider = "test"
    service.model = "test-model"
    service.client = MagicMock()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        completion = MagicMock()
        completion.choices[0].message.content = responses[
            min(len(calls) - 1, len(responses) - 1)
        ]
        return completion

    service.client.chat.completions.create.side_effect = create
    service._calls = calls
    return service


def make_entry(transcript: str):
    entry = MagicMock()
    entry.id = "e1"
    entry.title = "Test Entry"
    entry.transcript = transcript
    entry.speakers = None
    entry.additional_context = None
    return entry


class GenerateSummaryTests(TestCase):
    def test_single_chunk_uses_one_call(self):
        service = make_service(["short summary"])
        entry = make_entry("A short transcript. " * 5)
        result = run(service.generate_summary(entry))
        self.assertEqual(result, "short summary")
        self.assertEqual(len(service._calls), 1)
        # Full transcript present in the single-call prompt
        self.assertIn("short transcript", str(service._calls[0]["messages"]))

    def test_multi_chunk_maps_then_reduces(self):
        service = make_service(["extracted points", "final complete summary"])
        # Force multiple chunks with small settings
        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.summary_chunk_size = 50
            mock_settings.summary_chunk_overlap = 5
            entry = make_entry("This sentence fills the chunk nicely. " * 40)
            result = run(service.generate_summary(entry))
        self.assertEqual(result, "final complete summary")
        # more than one call: N map calls + 1 reduce
        self.assertGreater(len(service._calls), 2)

    def test_failed_map_chunk_noted_as_gap(self):
        # Chunk 1 fails on both attempts (map calls run in parallel, so the
        # failure must key on the chunk's own prompt, not call order)
        def create(**kwargs):
            if "section 1 of" in str(kwargs["messages"]):
                raise RuntimeError("api down")
            completion = MagicMock()
            completion.choices[0].message.content = "ok"
            return completion

        service = make_service(["unused"])
        service.client.chat.completions.create.side_effect = create
        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.summary_chunk_size = 50
            mock_settings.summary_chunk_overlap = 5
            entry = make_entry("This sentence fills the chunk nicely. " * 40)
            run(service.generate_summary(entry))
        # The reduce prompt must mention the unavailable section
        final_prompt = str(service.client.chat.completions.create.call_args)
        self.assertIn("unavailable", final_prompt)
