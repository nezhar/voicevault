import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_service(response_fn):
    from app.services.chat_service import ChatService

    service = ChatService.__new__(ChatService)
    service.provider = "test"
    service.model = "test-model"
    service.client = MagicMock()

    def create(**kwargs):
        completion = MagicMock()
        completion.choices[0].message.content = response_fn(kwargs)
        return completion

    service.client.chat.completions.create.side_effect = create
    return service


def make_entry(transcript: str):
    entry = MagicMock()
    entry.id = "e1"
    entry.title = "Test Entry"
    entry.transcript = transcript
    entry.speakers = None
    entry.additional_context = None
    return entry


async def collect(agen):
    return [event async for event in agen]


class ChatStreamTests(TestCase):
    def test_single_chunk_short_transcript(self):
        service = make_service(lambda kwargs: "the answer")
        entry = make_entry("Short transcript content.")
        events = run(collect(service.chat_with_entry_stream(entry, "What is said?")))

        types = [(e["type"], e.get("stage")) for e in events]
        self.assertEqual(
            types,
            [
                ("progress", "map"),
                ("progress", "reduce"),
                ("answer", None),
                ("done", None),
            ],
        )
        self.assertEqual(
            events[0],
            {"type": "progress", "stage": "map", "done": 0, "total": 1},
        )
        self.assertEqual(events[2]["content"], "the answer")

    def test_multi_chunk_emits_progress_per_chunk(self):
        def respond(kwargs):
            prompt = str(kwargs["messages"])
            if "TRANSCRIPT SECTION" in prompt:
                return "relevant note"
            return "final answer"

        service = make_service(respond)
        entry = make_entry("This sentence fills the chunk nicely. " * 40)
        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.chat_chunk_size = 50
            mock_settings.chat_chunk_overlap = 5
            events = run(collect(service.chat_with_entry_stream(entry, "topic?")))

        map_events = [
            e for e in events if e["type"] == "progress" and e["stage"] == "map"
        ]
        total = map_events[0]["total"]
        self.assertGreater(total, 1)
        # initial 0/N plus one event per completed chunk
        self.assertEqual([e["done"] for e in map_events], list(range(total + 1)))
        self.assertEqual(events[-2]["type"], "answer")
        self.assertEqual(events[-2]["content"], "final answer")
        self.assertEqual(events[-1], {"type": "done"})

    def test_all_none_partials_still_answers(self):
        def respond(kwargs):
            prompt = str(kwargs["messages"])
            if "TRANSCRIPT SECTION" in prompt:
                return "NONE"
            return "not covered in transcript"

        service = make_service(respond)
        entry = make_entry("This sentence fills the chunk nicely. " * 40)
        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.chat_chunk_size = 50
            mock_settings.chat_chunk_overlap = 5
            events = run(collect(service.chat_with_entry_stream(entry, "unrelated?")))

        answer = [e for e in events if e["type"] == "answer"][0]
        self.assertEqual(answer["content"], "not covered in transcript")

    def test_history_reaches_reduce_only(self):
        captured = []

        def respond(kwargs):
            captured.append(kwargs["messages"])
            prompt = str(kwargs["messages"])
            return "note" if "TRANSCRIPT SECTION" in prompt else "answer"

        service = make_service(respond)
        entry = make_entry("This sentence fills the chunk nicely. " * 40)
        history = [{"role": "user", "content": "earlier question"}]
        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.chat_chunk_size = 50
            mock_settings.chat_chunk_overlap = 5
            run(collect(service.chat_with_entry_stream(entry, "next?", history)))

        map_prompts = [m for m in captured if "TRANSCRIPT SECTION" in str(m)]
        reduce_prompts = [m for m in captured if "TRANSCRIPT SECTION" not in str(m)]
        for prompt in map_prompts:
            self.assertNotIn("earlier question", str(prompt))
        self.assertIn("earlier question", str(reduce_prompts))
