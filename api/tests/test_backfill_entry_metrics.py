import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.scripts.backfill_entry_metrics import backfill, compute_missing_metrics

ORIGINAL_UPDATED_AT = datetime(2024, 3, 4, 5, 6, 7)


def make_entry(**overrides):
    defaults = {
        "id": uuid4(),
        "file_path": "uploads/abc.mp3",
        "file_size_bytes": None,
        "duration_seconds": None,
        "word_count": None,
        "transcript": None,
        "transcript_words": None,
        "transcript_segments": None,
        "updated_at": ORIGINAL_UPDATED_AT,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_db(*batches):
    """A Session mock whose query chain returns the given batches in order.

    Every chained builder method returns the same query mock, so the batch a
    call receives depends only on how many times ``.all()`` has been called —
    not on which optional filters that particular fetch happened to add.
    """

    query = MagicMock()
    for method in ("filter", "options", "order_by", "offset", "limit"):
        getattr(query, method).return_value = query
    query.all.side_effect = [list(batch) for batch in batches]

    db = MagicMock()
    db.query.return_value = query
    return db, query


class ComputeMissingMetricsTests(TestCase):
    def test_derives_all_three_metrics(self):
        s3 = MagicMock()
        s3.get_file_info.return_value = {"size": 4096}
        entry = make_entry(
            transcript="one two three",
            transcript_words=json.dumps([{"word": "one"}, {"word": "two"}]),
            transcript_segments=json.dumps([{"end": 1.0}, {"end": 8.5}]),
        )

        result = compute_missing_metrics(entry, s3)

        self.assertEqual(
            result,
            {"file_size_bytes": 4096, "duration_seconds": 8.5, "word_count": 2},
        )

    def test_skips_fields_that_are_already_populated(self):
        s3 = MagicMock()
        entry = make_entry(
            file_size_bytes=10,
            duration_seconds=20.0,
            word_count=30,
            transcript="one two three",
        )

        self.assertEqual(compute_missing_metrics(entry, s3), {})
        s3.get_file_info.assert_not_called()

    def test_skips_size_when_the_entry_has_no_stored_file(self):
        s3 = MagicMock()
        entry = make_entry(file_path=None, transcript="one two")

        result = compute_missing_metrics(entry, s3)

        self.assertEqual(result, {"word_count": 2})
        s3.get_file_info.assert_not_called()

    def test_omits_size_when_the_object_is_missing_from_s3(self):
        s3 = MagicMock()
        s3.get_file_info.return_value = None
        entry = make_entry(transcript="one two")

        result = compute_missing_metrics(entry, s3)

        self.assertEqual(result, {"word_count": 2})

    def test_falls_back_to_the_transcript_when_word_json_is_malformed(self):
        s3 = MagicMock()
        s3.get_file_info.return_value = {"size": 1}
        entry = make_entry(transcript="one two three", transcript_words="{oops")

        result = compute_missing_metrics(entry, s3)

        self.assertEqual(result["word_count"], 3)

    def test_returns_nothing_derivable_for_an_untranscribed_entry(self):
        s3 = MagicMock()
        s3.get_file_info.return_value = {"size": 512}
        entry = make_entry()

        self.assertEqual(compute_missing_metrics(entry, s3), {"file_size_bytes": 512})


class BackfillTests(TestCase):
    def test_an_s3_failure_on_one_entry_does_not_abort_the_run(self):
        doomed = make_entry(transcript="one two")
        later = make_entry(transcript="three four five")
        db, _ = make_db([doomed, later])
        s3 = MagicMock()
        s3.get_file_info.side_effect = [
            OSError("bucket unreachable"),
            {"size": 2048},
        ]

        counters = backfill(db, s3)

        self.assertEqual(counters, {"scanned": 2, "updated": 1, "failed": 1})
        # The entry after the failure was still examined and still written.
        self.assertEqual(s3.get_file_info.call_count, 2)
        self.assertEqual(db.execute.call_count, 1)
        db.commit.assert_called_once()

    def test_counts_scanned_updated_and_failed(self):
        derivable = make_entry(transcript="one two")
        nothing_derivable = make_entry(file_path=None)
        broken = make_entry(transcript="three")
        db, _ = make_db([derivable, nothing_derivable, broken])
        s3 = MagicMock()
        s3.get_file_info.side_effect = [{"size": 1}, RuntimeError("boom")]

        counters = backfill(db, s3)

        self.assertEqual(counters, {"scanned": 3, "updated": 1, "failed": 1})
        # Only the derivable entry produced a write.
        self.assertEqual(db.execute.call_count, 1)

    def test_a_real_run_commits(self):
        db, _ = make_db([make_entry(file_path=None, transcript="one two")])

        backfill(db, MagicMock())

        db.commit.assert_called_once()
        db.rollback.assert_not_called()

    def test_commits_once_per_batch(self):
        entries = [make_entry(file_path=None, transcript="one two") for _ in range(3)]
        db, _ = make_db(entries[:2], entries[2:])

        counters = backfill(db, MagicMock(), batch_size=2)

        self.assertEqual(counters["scanned"], 3)
        self.assertEqual(db.commit.call_count, 2)

    def test_dry_run_rolls_back_and_never_commits_or_writes(self):
        db, _ = make_db([make_entry(file_path=None, transcript="one two")])

        counters = backfill(db, MagicMock(), dry_run=True)

        self.assertEqual(counters, {"scanned": 1, "updated": 1, "failed": 0})
        db.commit.assert_not_called()
        db.execute.assert_not_called()
        db.rollback.assert_called_once()

    def test_preserves_the_existing_updated_at(self):
        entry = make_entry(file_path=None, transcript="one two")
        db, _ = make_db([entry])

        backfill(db, MagicMock())

        statement = db.execute.call_args.args[0]
        params = statement.compile().params
        self.assertEqual(params["word_count"], 2)
        # Naming updated_at in values() suppresses the column's onupdate.
        self.assertEqual(params["updated_at"], ORIGINAL_UPDATED_AT)

    def test_limit_bounds_the_entries_examined(self):
        entries = [make_entry(file_path=None, transcript="one two") for _ in range(2)]
        db, query = make_db(entries)

        counters = backfill(db, MagicMock(), limit=2)

        self.assertEqual(counters["scanned"], 2)
        # The limit caps the fetch and the run stops rather than paging on.
        query.limit.assert_called_once_with(2)
        self.assertEqual(query.all.call_count, 1)

    def test_a_limit_of_zero_examines_nothing(self):
        db, _ = make_db([make_entry(transcript="one two")])

        counters = backfill(db, MagicMock(), limit=0)

        self.assertEqual(counters, {"scanned": 0, "updated": 0, "failed": 0})
        db.query.assert_not_called()
        db.commit.assert_not_called()
        db.rollback.assert_not_called()

    def test_offset_skips_matching_entries_and_applies_only_once(self):
        first = make_entry(file_path=None, transcript="one two")
        second = make_entry(file_path=None, transcript="three four")
        db, query = make_db([first], [second], [])

        counters = backfill(db, MagicMock(), offset=5, batch_size=1)

        self.assertEqual(counters["scanned"], 2)
        # Later batches page with the id cursor, not a growing OFFSET.
        self.assertEqual(query.offset.call_args_list, [call(5)])


class RunOnStartupTests(TestCase):
    """The wrapper the API lifespan launches in a worker thread."""

    def setUp(self):
        self.lock_conn = MagicMock()
        self.set_lock_acquired(True)
        self.engine = MagicMock()
        self.engine.connect.return_value = self.lock_conn
        self.counters = {"scanned": 3, "updated": 2, "failed": 0}

    def set_lock_acquired(self, acquired: bool) -> None:
        self.lock_conn.exec_driver_sql.return_value.scalar.return_value = acquired

    def run_startup(self, backfill_impl=None):
        module = sys.modules["app.scripts.backfill_entry_metrics"]
        backfill_mock = MagicMock(
            side_effect=backfill_impl,
            return_value=self.counters,
        )
        with patch.multiple(
            module,
            engine=self.engine,
            SessionLocal=MagicMock(),
            S3Service=MagicMock(),
            backfill=backfill_mock,
        ):
            return module.run_on_startup(), backfill_mock

    def test_runs_the_backfill_and_returns_its_counters(self):
        result, backfill_mock = self.run_startup()

        self.assertEqual(result, self.counters)
        backfill_mock.assert_called_once()

    def test_skips_the_pass_when_another_process_holds_the_lock(self):
        self.set_lock_acquired(False)

        result, backfill_mock = self.run_startup()

        self.assertIsNone(result)
        backfill_mock.assert_not_called()

    def test_a_failed_pass_returns_none_instead_of_raising(self):
        # Startup must survive a broken S3 or an unreachable database.
        result, _ = self.run_startup(backfill_impl=RuntimeError("s3 is down"))

        self.assertIsNone(result)

    def test_releases_the_lock_and_closes_its_connection(self):
        for label, impl in (("success", None), ("failure", RuntimeError("boom"))):
            with self.subTest(outcome=label):
                self.setUp()
                self.run_startup(backfill_impl=impl)

                unlocks = [
                    args[0]
                    for args, _ in self.lock_conn.exec_driver_sql.call_args_list
                    if "pg_advisory_unlock" in args[0]
                ]
                self.assertEqual(len(unlocks), 1)
                self.lock_conn.close.assert_called_once()

    def test_takes_the_lock_on_its_own_connection_not_the_backfill_session(self):
        # The backfill commits per batch, which returns its connection to the
        # pool; a lock taken there would not survive the first commit.
        module = sys.modules["app.scripts.backfill_entry_metrics"]
        session_factory = MagicMock()
        with patch.multiple(
            module,
            engine=self.engine,
            SessionLocal=session_factory,
            S3Service=MagicMock(),
            backfill=MagicMock(return_value=self.counters),
        ):
            module.run_on_startup()

        self.engine.connect.assert_called_once_with()
        session_factory.return_value.close.assert_called_once()
