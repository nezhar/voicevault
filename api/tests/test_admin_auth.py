import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.api.routes import auth as auth_routes
from app.core import auth as auth_module
from app.core.config import AuthMode, Settings


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files from leaking into tests
    return Settings(_env_file=None, **overrides)


class AdminEmailsSettingTests(TestCase):
    def test_empty_value_yields_no_admins(self):
        self.assertEqual(make_settings(admin_emails="").admin_emails_list, [])

    def test_splits_strips_and_lowercases(self):
        settings = make_settings(admin_emails=" Ada@Corp.COM , bob@corp.com ")

        self.assertEqual(
            settings.admin_emails_list,
            ["ada@corp.com", "bob@corp.com"],
        )

    def test_ignores_empty_segments(self):
        settings = make_settings(admin_emails="ada@corp.com,,  ,bob@corp.com,")

        self.assertEqual(
            settings.admin_emails_list,
            ["ada@corp.com", "bob@corp.com"],
        )


def make_user(email: str, is_system: bool = False) -> SimpleNamespace:
    return SimpleNamespace(email=email, display_name="Ada", is_system=is_system)


class IsAdminEmailTests(TestCase):
    def check(self, mode: AuthMode, admin_emails: str, email: str | None) -> bool:
        settings = make_settings(auth_mode=mode, admin_emails=admin_emails)
        with patch.object(auth_module, "settings", settings):
            return auth_module.is_admin_email(email)

    def test_false_for_missing_email(self):
        for email in (None, ""):
            with self.subTest(email=email):
                self.assertFalse(self.check(AuthMode.OIDC, "ada@corp.com", email))

    def test_false_outside_oidc_mode_even_for_listed_admin(self):
        # ADMIN_EMAILS is an OIDC-only concept; the shared-user modes grant
        # admin through is_admin_user instead.
        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                self.assertFalse(self.check(mode, "ada@corp.com", "ada@corp.com"))


class IsAdminUserTests(TestCase):
    def check(self, mode: AuthMode, admin_emails: str, user: SimpleNamespace) -> bool:
        settings = make_settings(auth_mode=mode, admin_emails=admin_emails)
        with patch.object(auth_module, "settings", settings):
            return auth_module.is_admin_user(user)

    def test_shared_local_user_is_admin_outside_oidc_mode(self):
        user = make_user("local@voicevault.local", is_system=True)

        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                self.assertTrue(self.check(mode, "", user))

    def test_leftover_oidc_users_are_not_admin_outside_oidc_mode(self):
        # A database switched from oidc back to token still holds real users;
        # only the shared local account is the operator.
        user = make_user("ada@corp.com", is_system=False)

        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                self.assertFalse(self.check(mode, "ada@corp.com", user))

    def test_oidc_mode_ignores_is_system_and_uses_admin_emails(self):
        self.assertTrue(
            self.check(AuthMode.OIDC, "ada@corp.com", make_user("ada@corp.com")),
        )
        self.assertFalse(
            self.check(
                AuthMode.OIDC,
                "ada@corp.com",
                make_user("bob@corp.com", is_system=True),
            ),
        )


class RequireAdminTests(TestCase):
    def call(self, mode: AuthMode, admin_emails: str, user: SimpleNamespace):
        settings = make_settings(auth_mode=mode, admin_emails=admin_emails)
        with patch.object(auth_module, "settings", settings):
            return auth_module.require_admin(user)

    def test_returns_the_same_user_for_listed_admin(self):
        user = make_user("ada@corp.com")

        self.assertIs(self.call(AuthMode.OIDC, "ada@corp.com", user), user)

    def test_matches_regardless_of_config_case_and_whitespace(self):
        user = make_user("ada@corp.com")

        self.assertIs(self.call(AuthMode.OIDC, "  Ada@Corp.com ", user), user)

    def test_matches_regardless_of_user_case_and_whitespace(self):
        user = make_user("Ada@Corp.com ")

        self.assertIs(self.call(AuthMode.OIDC, "ada@corp.com", user), user)

    def test_404_for_non_admin(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(AuthMode.OIDC, "ada@corp.com", make_user("bob@corp.com"))

        self.assertEqual(caught.exception.status_code, 404)

    def test_404_when_admin_emails_is_empty(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(AuthMode.OIDC, "", make_user("ada@corp.com"))

        self.assertEqual(caught.exception.status_code, 404)

    def test_admits_the_shared_local_user_outside_oidc_mode(self):
        user = make_user("local@voicevault.local", is_system=True)

        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                self.assertIs(self.call(mode, "", user), user)

    def test_404_for_leftover_oidc_users_outside_oidc_mode(self):
        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                with self.assertRaises(HTTPException) as caught:
                    self.call(mode, "ada@corp.com", make_user("ada@corp.com"))

                self.assertEqual(caught.exception.status_code, 404)


class UserResponseAdminFlagTests(TestCase):
    def test_marks_listed_admin(self):
        settings = make_settings(auth_mode=AuthMode.OIDC, admin_emails="ada@corp.com")
        user = SimpleNamespace(
            id=uuid4(),
            email="ada@corp.com",
            display_name="Ada",
        )

        with patch.object(auth_module, "settings", settings):
            response = auth_routes.build_user_response(user)

        self.assertTrue(response.is_admin)

    def test_does_not_mark_other_users(self):
        settings = make_settings(auth_mode=AuthMode.OIDC, admin_emails="ada@corp.com")
        user = SimpleNamespace(
            id=uuid4(),
            email="bob@corp.com",
            display_name="Bob",
        )

        with patch.object(auth_module, "settings", settings):
            response = auth_routes.build_user_response(user)

        self.assertFalse(response.is_admin)

    def test_marks_the_shared_local_user_outside_oidc_mode(self):
        # Drives the Admin entry in the UI sidebar, which reads /api/auth/me.
        user = SimpleNamespace(
            id=uuid4(),
            email="local@voicevault.local",
            display_name="Local User",
            is_system=True,
        )

        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                settings = make_settings(auth_mode=mode, admin_emails="")
                with patch.object(auth_module, "settings", settings):
                    response = auth_routes.build_user_response(user)

                self.assertTrue(response.is_admin)

    def test_does_not_mark_leftover_oidc_users_outside_oidc_mode(self):
        user = SimpleNamespace(
            id=uuid4(),
            email="ada@corp.com",
            display_name="Ada",
            is_system=False,
        )

        for mode in (AuthMode.NONE, AuthMode.TOKEN):
            with self.subTest(mode=mode):
                settings = make_settings(
                    auth_mode=mode,
                    admin_emails="ada@corp.com",
                )
                with patch.object(auth_module, "settings", settings):
                    response = auth_routes.build_user_response(user)

                self.assertFalse(response.is_admin)
