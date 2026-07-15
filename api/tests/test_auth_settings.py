import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import AuthMode, Settings, validate_auth_settings


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files from leaking into tests
    return Settings(_env_file=None, **overrides)


class EffectiveAuthModeTests(TestCase):
    def test_defaults_to_none_without_access_token(self):
        settings = make_settings(access_token=None)
        self.assertEqual(settings.effective_auth_mode, AuthMode.NONE)

    def test_defaults_to_token_with_access_token(self):
        settings = make_settings(access_token="secret")
        self.assertEqual(settings.effective_auth_mode, AuthMode.TOKEN)

    def test_explicit_mode_wins(self):
        settings = make_settings(access_token="secret", auth_mode=AuthMode.OIDC)
        self.assertEqual(settings.effective_auth_mode, AuthMode.OIDC)

    def test_empty_string_mode_is_treated_as_unset(self):
        # docker compose forwards unset variables as empty strings
        settings = make_settings(access_token="secret", auth_mode="")
        self.assertEqual(settings.effective_auth_mode, AuthMode.TOKEN)

        settings = make_settings(access_token=None, auth_mode="")
        self.assertEqual(settings.effective_auth_mode, AuthMode.NONE)


class CorsOriginsTests(TestCase):
    def test_splits_and_strips_origins(self):
        settings = make_settings(cors_origins="http://a.test, http://b.test")
        self.assertEqual(settings.cors_origins_list, ["http://a.test", "http://b.test"])


class ValidateAuthSettingsTests(TestCase):
    def test_oidc_mode_requires_all_variables(self):
        settings = make_settings(auth_mode=AuthMode.OIDC)
        with patch("app.core.config.settings", settings):
            with self.assertRaisesRegex(RuntimeError, "OIDC_DISCOVERY_URL"):
                validate_auth_settings()

    def test_oidc_mode_passes_with_all_variables(self):
        settings = make_settings(
            auth_mode=AuthMode.OIDC,
            oidc_discovery_url="https://idp.test/.well-known/openid-configuration",
            oidc_client_id="voicevault",
            oidc_client_secret="secret",
            session_secret="cookie-secret",
            public_base_url="https://voicevault.test",
        )
        with patch("app.core.config.settings", settings):
            validate_auth_settings()  # must not raise

    def test_token_mode_needs_no_oidc_variables(self):
        settings = make_settings(access_token="secret")
        with patch("app.core.config.settings", settings):
            validate_auth_settings()  # must not raise
