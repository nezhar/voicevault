import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes import auth as auth_routes
from app.core.config import AuthMode


class AuthConfigTests(IsolatedAsyncioTestCase):
    @patch.object(auth_routes.settings, "auth_mode", AuthMode.OIDC)
    async def test_reports_effective_mode(self):
        result = await auth_routes.get_auth_config()
        self.assertEqual(result.mode, "oidc")


class OidcCallbackTests(IsolatedAsyncioTestCase):
    def _request(self):
        return SimpleNamespace(cookies={})

    @patch.object(auth_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch.object(auth_routes.settings, "initial_owner_email", "admin@corp")
    @patch.object(auth_routes.settings, "session_cookie_secure", False)
    @patch("app.api.routes.auth.SessionService")
    @patch("app.api.routes.auth.UserService")
    @patch("app.api.routes.auth.get_oauth")
    async def test_successful_callback_sets_cookie_and_claims_legacy(
        self,
        get_oauth_mock,
        user_service_mock,
        session_service_mock,
    ):
        get_oauth_mock.return_value.oidc.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "iss": "https://idp.test",
                    "sub": "u1",
                    "email": "Admin@Corp",
                    "name": "Admin",
                },
            },
        )
        user = SimpleNamespace(id=uuid4(), email="admin@corp", is_system=False)
        user_service_mock.return_value.provision_oidc_user.return_value = user
        session_service_mock.return_value.create_session.return_value = (
            SimpleNamespace(id="hashed-session-id"),
            "session-id",
        )

        response = await auth_routes.oidc_callback(self._request(), MagicMock())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")
        self.assertIn("voicevault_session=session-id", response.headers["set-cookie"])
        user_service_mock.return_value.claim_legacy_entries.assert_called_once_with(
            user,
        )

    @patch.object(auth_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.auth.get_oauth")
    async def test_failed_token_exchange_redirects_with_error_code(
        self,
        get_oauth_mock,
    ):
        get_oauth_mock.return_value.oidc.authorize_access_token = AsyncMock(
            side_effect=Exception("boom"),
        )

        response = await auth_routes.oidc_callback(self._request(), MagicMock())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "/?auth_error=token_exchange_failed",
        )

    @patch.object(auth_routes.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.api.routes.auth.UserService")
    @patch("app.api.routes.auth.get_oauth")
    async def test_provisioning_conflict_redirects_with_error_code(
        self,
        get_oauth_mock,
        user_service_mock,
    ):
        from sqlalchemy.exc import IntegrityError

        get_oauth_mock.return_value.oidc.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "iss": "https://idp.test",
                    "sub": "recreated-account",
                    "email": "taken@corp",
                    "name": "Someone",
                },
            },
        )
        user_service_mock.return_value.provision_oidc_user.side_effect = IntegrityError(
            "INSERT INTO users",
            {},
            Exception("duplicate email"),
        )
        db = MagicMock()

        response = await auth_routes.oidc_callback(self._request(), db)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "/?auth_error=provisioning_failed",
        )
        db.rollback.assert_called_once()

    @patch.object(auth_routes.settings, "auth_mode", AuthMode.TOKEN)
    async def test_login_endpoint_404_outside_oidc_mode(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            await auth_routes.oidc_login(self._request())
        self.assertEqual(ctx.exception.status_code, 404)


class LogoutTests(IsolatedAsyncioTestCase):
    @patch("app.api.routes.auth.SessionService")
    async def test_logout_deletes_session_and_clears_cookie(self, session_service_mock):
        request = SimpleNamespace(cookies={"voicevault_session": "abc"})

        response = await auth_routes.logout(request, MagicMock())

        session_service_mock.return_value.delete_session.assert_called_once_with("abc")
        self.assertIn("voicevault_session=", response.headers["set-cookie"])
