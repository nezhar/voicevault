import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core import auth as auth_module
from app.core.config import AuthMode, Settings
from app.models.entry import EntryStatus, SourceType
from app.services.admin_stats_service import (
    SORT_EXPRESSIONS,
    build_system_stats,
    build_user_stats,
    resolve_sort,
)


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files from leaking into tests
    return Settings(_env_file=None, **overrides)


class ResolveSortTests(TestCase):
    def test_accepts_every_documented_sort_key(self):
        for key in (
            "entry_count",
            "storage_bytes",
            "duration_seconds",
            "word_count",
            "email",
            "created_at",
        ):
            with self.subTest(key=key):
                self.assertIsNotNone(resolve_sort(key, "desc"))

    def test_rejects_a_sort_key_that_is_not_whitelisted(self):
        # The whitelist maps names to SQLAlchemy expressions; nothing is ever
        # interpolated, so an unknown column and an injection attempt take the
        # same path and can only 400.
        for key in ("password", "email; DROP TABLE users"):
            with self.subTest(key=key), self.assertRaises(HTTPException) as caught:
                resolve_sort(key, "asc")

            self.assertEqual(caught.exception.status_code, 400)

    def test_rejects_an_unknown_order(self):
        with self.assertRaises(HTTPException) as caught:
            resolve_sort("email", "sideways")

        self.assertEqual(caught.exception.status_code, 400)

    def test_order_decides_the_sort_direction(self):
        # Comparing the expressions with == (or testing them for truthiness)
        # is impossible: ColumnOperators.__bool__ raises TypeError. Render them
        # to SQL text instead, which is what actually reaches the database.
        descending = str(resolve_sort("email", "desc")).upper()
        ascending = str(resolve_sort("email", "asc")).upper()

        self.assertTrue(descending.endswith("DESC"), descending)
        self.assertTrue(ascending.endswith("ASC"), ascending)
        self.assertNotEqual(descending, ascending)

    def test_every_whitelisted_key_maps_to_an_orderable_expression(self):
        for key, expression in SORT_EXPRESSIONS.items():
            with self.subTest(key=key):
                self.assertTrue(callable(getattr(expression, "asc", None)))
                self.assertTrue(callable(getattr(expression, "desc", None)))


class BuildSystemStatsTests(TestCase):
    def test_zero_fills_missing_status_and_source_buckets(self):
        stats = build_system_stats(
            users_total=3,
            users_active_30d=2,
            users_new_30d=1,
            entry_totals=SimpleNamespace(
                entries_total=5,
                storage_bytes_total=100,
                duration_seconds_total=60.0,
                words_total=900,
                entries_archived=1,
                entries_missing_metrics=2,
                entries_unassigned=1,
            ),
            status_rows=[("READY", 4), ("ERROR", 1)],
            source_rows=[("upload", 5)],
            projects_total=2,
        )

        self.assertEqual(
            stats.entries_by_status,
            {"NEW": 0, "IN_PROGRESS": 0, "READY": 4, "COMPLETE": 0, "ERROR": 1},
        )
        self.assertEqual(stats.entries_by_source, {"upload": 5, "url": 0})
        self.assertEqual(stats.entries_total, 5)
        self.assertEqual(stats.entries_missing_metrics, 2)
        self.assertEqual(stats.entries_unassigned, 1)

    def test_unwraps_the_enum_members_sqlalchemy_actually_returns(self):
        # At runtime GROUP BY hands back EntryStatus/SourceType members, not
        # strings, and str(EntryStatus.READY) is "EntryStatus.READY" — so the
        # keys are only usable if build_system_stats reads .value.
        stats = build_system_stats(
            users_total=1,
            users_active_30d=1,
            users_new_30d=0,
            entry_totals=SimpleNamespace(
                entries_total=3,
                storage_bytes_total=10,
                duration_seconds_total=1.0,
                words_total=7,
                entries_archived=0,
                entries_missing_metrics=0,
                entries_unassigned=0,
            ),
            status_rows=[(EntryStatus.READY, 3)],
            source_rows=[(SourceType.URL, 3)],
            projects_total=0,
        )

        self.assertEqual(stats.entries_by_status["READY"], 3)
        self.assertEqual(stats.entries_by_source["url"], 3)
        self.assertNotIn("EntryStatus.READY", stats.entries_by_status)
        self.assertNotIn("SourceType.URL", stats.entries_by_source)

    def test_coerces_null_aggregates_to_zero(self):
        stats = build_system_stats(
            users_total=0,
            users_active_30d=0,
            users_new_30d=0,
            entry_totals=SimpleNamespace(
                entries_total=0,
                storage_bytes_total=None,
                duration_seconds_total=None,
                words_total=None,
                entries_archived=0,
                entries_missing_metrics=0,
                entries_unassigned=0,
            ),
            status_rows=[],
            source_rows=[],
            projects_total=0,
        )

        self.assertEqual(stats.storage_bytes_total, 0)
        self.assertEqual(stats.duration_seconds_total, 0.0)
        self.assertEqual(stats.words_total, 0)


class BuildUserStatsTests(TestCase):
    def make_row(self, **overrides):
        user_id = overrides.pop("user_id", uuid4())
        defaults = {
            "user_id": user_id,
            "email": "ada@corp.com",
            "display_name": "Ada",
            "is_system": False,
            "created_at": None,
            "last_login_at": None,
            "entry_count": 2,
            "storage_bytes": 2048,
            "duration_seconds": 120.0,
            "word_count": 500,
            "error_count": 1,
            "project_count": 3,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_flags_listed_admins(self):
        settings = make_settings(auth_mode=AuthMode.OIDC, admin_emails="ada@corp.com")

        with patch.object(auth_module, "settings", settings):
            rows = build_user_stats(
                [self.make_row(), self.make_row(email="bob@corp.com")],
            )

        self.assertTrue(rows[0].is_admin)
        self.assertFalse(rows[1].is_admin)

    def test_coerces_null_aggregates_to_zero(self):
        settings = make_settings(auth_mode=AuthMode.OIDC, admin_emails="")
        row = self.make_row(
            entry_count=0,
            storage_bytes=None,
            duration_seconds=None,
            word_count=None,
            error_count=0,
            project_count=0,
        )

        with patch.object(auth_module, "settings", settings):
            rows = build_user_stats([row])

        self.assertEqual(rows[0].storage_bytes, 0)
        self.assertEqual(rows[0].duration_seconds, 0.0)
        self.assertEqual(rows[0].word_count, 0)

    def test_preserves_the_system_flag(self):
        settings = make_settings(auth_mode=AuthMode.OIDC, admin_emails="")

        with patch.object(auth_module, "settings", settings):
            rows = build_user_stats([self.make_row(is_system=True)])

        self.assertTrue(rows[0].is_system)
