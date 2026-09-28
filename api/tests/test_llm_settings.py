import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import RETIRED_LLM_VARIABLES, Settings, validate_llm_settings


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files from leaking into tests.
    # LLM values default to None explicitly so a developer's shell environment
    # cannot make a "missing" test pass.
    values = {"llm_base_url": None, "llm_api_key": None, "llm_model": None}
    values.update(overrides)
    return Settings(_env_file=None, **values)


LEGACY_ENV = {
    "LLM_PROVIDER": "groq",
    "CEREBRAS_API_KEY": "key",
    "NEBIUS_API_KEY": "key",
    "OLLAMA_BASE_URL": "http://ollama:11434",
    "OLLAMA_MODEL": "llama3.2",
}


class LLMSettingsTests(TestCase):
    def test_empty_strings_are_treated_as_unset(self):
        # docker compose forwards unset variables as empty strings
        settings = make_settings(llm_base_url="", llm_api_key="", llm_model="")
        self.assertIsNone(settings.llm_base_url)
        self.assertIsNone(settings.llm_api_key)
        self.assertIsNone(settings.llm_model)

    def test_whitespace_only_strings_are_treated_as_unset(self):
        # Whitespace-only values (e.g. a stray newline from a secrets
        # manager) must not survive as truthy, or they reach an API client
        # constructor unvalidated and fail confusingly at request time
        # instead of at startup.
        settings = make_settings(llm_base_url="   ", llm_api_key="\t", llm_model="  ")
        self.assertIsNone(settings.llm_base_url)
        self.assertIsNone(settings.llm_api_key)
        self.assertIsNone(settings.llm_model)

    def test_whitespace_only_base_url_is_reported_as_missing(self):
        settings = make_settings(llm_base_url="   ", llm_model="m")
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                validate_llm_settings()
        self.assertIn("LLM_BASE_URL", str(ctx.exception))

    def test_values_are_kept(self):
        settings = make_settings(
            llm_base_url="http://llm.test/v1",
            llm_api_key="secret",
            llm_model="test-model",
        )
        self.assertEqual(settings.llm_base_url, "http://llm.test/v1")
        self.assertEqual(settings.llm_api_key, "secret")
        self.assertEqual(settings.llm_model, "test-model")


class LLMTuningSettingsTests(TestCase):
    """LLM_MAX_TOKENS and LLM_EXTRA_BODY, parsed from the environment the way
    docker compose delivers them (unset variables arrive as empty strings)."""

    def from_env(self, **env) -> Settings:
        with patch.dict(os.environ, env):
            return Settings(_env_file=None)

    def test_empty_values_are_unset(self):
        settings = self.from_env(LLM_MAX_TOKENS="", LLM_EXTRA_BODY=" ", LLM_TIMEOUT="")
        self.assertIsNone(settings.llm_max_tokens)
        self.assertIsNone(settings.llm_timeout)
        self.assertIsNone(settings.llm_extra_body)

    def test_values_are_parsed(self):
        settings = self.from_env(
            LLM_MAX_TOKENS="8192",
            LLM_TIMEOUT="280",
            LLM_EXTRA_BODY='{"chat_template_kwargs": {"enable_thinking": false}}',
        )
        self.assertEqual(settings.llm_max_tokens, 8192)
        self.assertEqual(settings.llm_timeout, 280.0)
        self.assertEqual(
            settings.llm_extra_body,
            {"chat_template_kwargs": {"enable_thinking": False}},
        )

    def test_invalid_values_are_rejected(self):
        for env in (
            {"LLM_MAX_TOKENS": "0"},
            {"LLM_MAX_TOKENS": "lots"},
            {"LLM_TIMEOUT": "0"},
            {"LLM_TIMEOUT": "-5"},
            {"LLM_TIMEOUT": "2m"},
            {"LLM_EXTRA_BODY": "enable_thinking=false"},
            {"LLM_EXTRA_BODY": "[1, 2]"},
        ):
            with self.subTest(env=env), self.assertRaises(ValidationError):
                self.from_env(**env)

    def test_python_style_extra_body_is_explained(self):
        # A Python dict repr (single quotes, True) is not JSON; the error has to
        # say so instead of pydantic's bare "Input should be a valid dictionary".
        with self.assertRaises(ValidationError) as ctx:
            self.from_env(
                LLM_EXTRA_BODY="{'chat_template_kwargs': {'enable_thinking': True}}",
            )
        message = str(ctx.exception)
        self.assertIn("LLM_EXTRA_BODY must be a JSON object", message)
        self.assertIn("double quotes", message)


class ValidateLLMSettingsTests(TestCase):
    def test_retired_table_covers_every_old_variable(self):
        self.assertEqual(set(RETIRED_LLM_VARIABLES), set(LEGACY_ENV))

    def test_passes_with_base_url_and_model_and_no_api_key(self):
        settings = make_settings(llm_base_url="http://llm.test/v1", llm_model="m")
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, {}, clear=True),
        ):
            validate_llm_settings()  # must not raise

    def test_reports_every_missing_required_variable(self):
        settings = make_settings()
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                validate_llm_settings()
        message = str(ctx.exception)
        self.assertIn("LLM_BASE_URL", message)
        self.assertIn("LLM_MODEL", message)

    def test_rejects_retired_variables_naming_their_replacement(self):
        settings = make_settings(llm_base_url="http://llm.test/v1", llm_model="m")
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, LEGACY_ENV, clear=True),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                validate_llm_settings()
        message = str(ctx.exception)
        self.assertIn("LLM_PROVIDER (use LLM_BASE_URL)", message)
        self.assertIn("CEREBRAS_API_KEY (use LLM_API_KEY)", message)
        self.assertIn("NEBIUS_API_KEY (use LLM_API_KEY)", message)
        self.assertIn("OLLAMA_BASE_URL (use LLM_BASE_URL)", message)
        self.assertIn("OLLAMA_MODEL (use LLM_MODEL)", message)

    def test_empty_retired_variables_are_ignored(self):
        # docker compose forwards unset variables as empty strings
        settings = make_settings(llm_base_url="http://llm.test/v1", llm_model="m")
        empty = {name: "" for name in LEGACY_ENV}
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, empty, clear=True),
        ):
            validate_llm_settings()  # must not raise

    def test_missing_and_retired_are_reported_together(self):
        settings = make_settings()
        with (
            patch("app.core.config.settings", settings),
            patch.dict(os.environ, {"OLLAMA_MODEL": "llama3.2"}, clear=True),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                validate_llm_settings()
        message = str(ctx.exception)
        self.assertIn("missing", message)
        self.assertIn("LLM_BASE_URL", message)
        self.assertIn("OLLAMA_MODEL (use LLM_MODEL)", message)


class DotEnvRejectsUnknownKeysTests(TestCase):
    def test_unknown_key_in_env_file_raises_before_validate_llm_settings_can_run(self):
        """Pins the guarantee documented above the retired-variable check in
        validate_llm_settings(): that function only ever sees a retired variable
        set via os.environ, never one left over in a .env file. A .env file is
        parsed by pydantic-settings itself (not written into os.environ), and
        with extra inputs forbidden, an unrecognised key there raises
        ValidationError at Settings() construction - i.e. at import time, well
        before validate_llm_settings() could run. If pydantic-settings ever
        stopped forbidding extra .env keys, this test would fail and flag that
        the os.environ-only comment/design needs revisiting.
        """
        unknown_key = "RETIRED_VARIABLE_NOT_A_DECLARED_SETTING"
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(f"{unknown_key}=some_value\n")
            with self.assertRaises(ValidationError) as ctx:
                Settings(_env_file=str(env_path))
        self.assertIn(unknown_key.lower(), str(ctx.exception).lower())
