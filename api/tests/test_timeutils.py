import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.timeutils import as_utc_iso
from app.models.schemas import PersonalAccessTokenResponse


class AsUTCISOTests(TestCase):
    def test_marks_a_naive_timestamp_as_utc(self):
        self.assertEqual(
            as_utc_iso(datetime(2026, 10, 4, 12, 0, 0)),
            "2026-10-04T12:00:00Z",
        )

    def test_keeps_sub_second_precision(self):
        self.assertEqual(
            as_utc_iso(datetime(2026, 10, 4, 12, 0, 0, 123456)),
            "2026-10-04T12:00:00.123456Z",
        )

    def test_converts_an_aware_timestamp_rather_than_relabelling_it(self):
        aware = datetime(2026, 10, 4, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(as_utc_iso(aware), "2026-10-04T12:00:00Z")


class ResponseSerializationTests(TestCase):
    """The wire format clients actually parse.

    A zone-less timestamp is read as *local* time by every JavaScript client,
    which shifts a token's expiry by the reader's UTC offset - enough to hide
    the controls on a token that is still valid.
    """

    def _response(self, **overrides):
        fields = {
            "id": uuid4(),
            "name": "CI",
            "token_prefix": "vvpat_abcdefghij",
            "permissions": ["entries.view"],
            "created_at": datetime(2026, 9, 4, 12, 0, 0),
            "expires_at": datetime(2026, 10, 4, 12, 0, 0),
            "last_used_at": None,
            "revoked_at": None,
        }
        fields.update(overrides)
        return PersonalAccessTokenResponse(**fields)

    def test_json_mode_marks_every_timestamp_as_utc(self):
        dumped = self._response().model_dump(mode="json")

        self.assertEqual(dumped["created_at"], "2026-09-04T12:00:00Z")
        self.assertEqual(dumped["expires_at"], "2026-10-04T12:00:00Z")
        self.assertIsNone(dumped["last_used_at"])
        self.assertIsNone(dumped["revoked_at"])

    def test_python_mode_still_yields_datetimes(self):
        # PersonalAccessTokenCreated.from_pat round-trips through this dump.
        dumped = self._response().model_dump()

        self.assertIsInstance(dumped["created_at"], datetime)
        self.assertIsInstance(dumped["expires_at"], datetime)
