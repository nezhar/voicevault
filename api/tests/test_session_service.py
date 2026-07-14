import sys
from datetime import timedelta

from app.core.timeutils import utcnow
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.session_service import (
    SESSION_COOKIE_NAME,
    SessionService,
    hash_session_token,
)


class CreateSessionTests(TestCase):
    def test_creates_opaque_session_and_purges_expired(self):
        db = MagicMock()
        user_id = uuid4()

        session, token = SessionService(db).create_session(user_id)

        added = db.add.call_args.args[0]
        self.assertGreaterEqual(len(token), 32)
        # only the hash is stored; the raw token goes into the cookie
        self.assertEqual(added.id, hash_session_token(token))
        self.assertNotEqual(added.id, token)
        self.assertEqual(added.user_id, user_id)
        self.assertGreater(added.expires_at, utcnow())
        # opportunistic cleanup of expired sessions happened
        db.query.return_value.filter.return_value.delete.assert_called_once()
        db.commit.assert_called_once()
        self.assertIs(session, added)


class GetValidSessionTests(TestCase):
    def test_returns_none_for_unknown_id(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        self.assertIsNone(SessionService(db).get_valid_session("nope"))

    def test_returns_none_and_deletes_expired_session(self):
        db = MagicMock()
        expired = SimpleNamespace(
            id="abc",
            expires_at=utcnow() - timedelta(hours=1),
        )
        db.query.return_value.filter.return_value.first.return_value = expired

        result = SessionService(db).get_valid_session("abc")

        self.assertIsNone(result)
        db.delete.assert_called_once_with(expired)

    def test_returns_valid_session(self):
        db = MagicMock()
        valid = SimpleNamespace(
            id="abc",
            expires_at=utcnow() + timedelta(hours=1),
        )
        db.query.return_value.filter.return_value.first.return_value = valid

        self.assertIs(SessionService(db).get_valid_session("abc"), valid)


class CookieNameTests(TestCase):
    def test_cookie_name_is_stable(self):
        self.assertEqual(SESSION_COOKIE_NAME, "voicevault_session")
