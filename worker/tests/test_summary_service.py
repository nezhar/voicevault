import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_service(responses):
    from app.services.summary_service import SummaryService

    service = SummaryService.__new__(SummaryService)
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


class SummaryServiceTests(TestCase):
    def test_short_transcript_single_call(self):
        service = make_service(["short summary"])
        result = run(service.generate_summary("A short transcript.", title="T"))
        self.assertEqual(result, "short summary")
        self.assertEqual(len(service._calls), 1)

    def test_long_transcript_map_reduce(self):
        service = make_service(["notes", "complete summary"])
        text = "This sentence fills the chunk nicely. " * 40
        with patch("app.services.summary_service.settings") as mock_settings:
            mock_settings.summary_chunk_size = 50
            mock_settings.summary_chunk_overlap = 5
            result = run(service.generate_summary(text, title="Long"))
        self.assertEqual(result, "complete summary")
        self.assertGreater(len(service._calls), 2)

    def test_metadata_in_prompt(self):
        service = make_service(["s"])
        run(
            service.generate_summary(
                "Short.",
                title="T",
                speakers="Alice, Bob",
                additional_context="board meeting",
            ),
        )
        prompt = str(service._calls[0]["messages"])
        self.assertIn("Alice, Bob", prompt)
        self.assertIn("board meeting", prompt)
