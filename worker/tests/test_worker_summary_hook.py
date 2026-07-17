import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.worker_service import WorkerService


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_worker():
    worker = WorkerService.__new__(WorkerService)
    worker.summary_service = MagicMock()
    worker.summary_service.generate_summary = AsyncMock(return_value="the summary")
    return worker


def make_entry():
    entry = MagicMock()
    entry.id = "e1"
    entry.title = "T"
    entry.speakers = None
    entry.additional_context = None
    return entry


class SummaryHookTests(TestCase):
    def test_summary_stored_after_ready(self):
        worker = make_worker()
        entry_service = MagicMock()
        entry_service.update_entry_summary = AsyncMock(return_value=True)

        run(
            worker.generate_entry_summary(
                make_entry(),
                "transcript text",
                entry_service,
            ),
        )

        worker.summary_service.generate_summary.assert_awaited_once()
        entry_service.update_entry_summary.assert_awaited_once_with(
            "e1",
            "the summary",
        )

    def test_summary_failure_is_swallowed(self):
        worker = make_worker()
        worker.summary_service.generate_summary = AsyncMock(
            side_effect=RuntimeError("llm down"),
        )
        entry_service = MagicMock()
        entry_service.update_entry_summary = AsyncMock()

        # Must not raise — entry stays READY with summary null
        run(
            worker.generate_entry_summary(
                make_entry(),
                "transcript text",
                entry_service,
            ),
        )
        entry_service.update_entry_summary.assert_not_awaited()

    def test_no_summary_service_is_noop(self):
        worker = WorkerService.__new__(WorkerService)
        worker.summary_service = None
        entry_service = MagicMock()
        entry_service.update_entry_summary = AsyncMock()

        run(
            worker.generate_entry_summary(
                make_entry(),
                "transcript text",
                entry_service,
            ),
        )
        entry_service.update_entry_summary.assert_not_awaited()
