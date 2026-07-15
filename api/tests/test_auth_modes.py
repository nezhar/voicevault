import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core import auth as auth_module
from app.core.config import AuthMode


def make_request(cookies=None):
    return SimpleNamespace(cookies=cookies or {})


def make_credentials(token):
    return SimpleNamespace(credentials=token)


class NoneModeTests(TestCase):
    @patch.object(auth_module.settings, "auth_mode", AuthMode.NONE)
    @patch("app.core.auth.UserService")
    def test_returns_system_user(self, user_service_mock):
        system_user = SimpleNamespace(id=uuid4(), is_system=True)
        user_service_mock.return_value.get_or_create_system_user.return_value = (
            system_user
        )

        result = auth_module.get_current_user(make_request(), None, MagicMock())

        self.assertIs(result, system_user)


class TokenModeTests(TestCase):
    @patch.object(auth_module.settings, "auth_mode", AuthMode.TOKEN)
    @patch.object(auth_module.settings, "access_token", "secret")
    @patch("app.core.auth.UserService")
    def test_valid_token_returns_system_user(self, user_service_mock):
        system_user = SimpleNamespace(id=uuid4(), is_system=True)
        user_service_mock.return_value.get_or_create_system_user.return_value = (
            system_user
        )

        result = auth_module.get_current_user(
            make_request(),
            make_credentials("secret"),
            MagicMock(),
        )

        self.assertIs(result, system_user)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.TOKEN)
    @patch.object(auth_module.settings, "access_token", "secret")
    def test_missing_or_wrong_token_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            auth_module.get_current_user(make_request(), None, MagicMock())
        self.assertEqual(ctx.exception.status_code, 401)

        with self.assertRaises(HTTPException) as ctx:
            auth_module.get_current_user(
                make_request(),
                make_credentials("wrong"),
                MagicMock(),
            )
        self.assertEqual(ctx.exception.status_code, 401)


class OidcModeTests(TestCase):
    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    def test_missing_cookie_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            auth_module.get_current_user(make_request(), None, MagicMock())
        self.assertEqual(ctx.exception.status_code, 401)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.SessionService")
    def test_invalid_session_raises_401(self, session_service_mock):
        session_service_mock.return_value.get_valid_session.return_value = None
        request = make_request(cookies={"voicevault_session": "expired"})

        with self.assertRaises(HTTPException) as ctx:
            auth_module.get_current_user(request, None, MagicMock())
        self.assertEqual(ctx.exception.status_code, 401)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.SessionService")
    def test_valid_session_returns_user(self, session_service_mock):
        user = SimpleNamespace(id=uuid4(), is_system=False)
        auth_session = SimpleNamespace(id="abc", user_id=user.id)
        session_service_mock.return_value.get_valid_session.return_value = auth_session
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        request = make_request(cookies={"voicevault_session": "abc"})

        result = auth_module.get_current_user(request, None, db)

        self.assertIs(result, user)
