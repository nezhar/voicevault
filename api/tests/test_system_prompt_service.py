import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.system_prompt import SystemPrompt
from app.services.system_prompt_service import DEFAULT_PROMPTS, SystemPromptService


class SystemPromptModelTests(TestCase):
    def test_model_has_expected_columns(self):
        cols = {c.name for c in SystemPrompt.__table__.columns}
        self.assertEqual(cols, {"task", "body", "updated_at"})

    def test_task_is_primary_key(self):
        pk_cols = {c.name for c in SystemPrompt.__table__.primary_key.columns}
        self.assertEqual(pk_cols, {"task"})


class SystemPromptServiceTests(TestCase):
    def make_row(self, task="chat", body="custom body"):
        return SimpleNamespace(task=task, body=body)

    def make_entry(
        self,
        title="Demo entry",
        transcript="Hello world",
        speakers="Alice, Bob",
        additional_context="Standup notes",
    ):
        return SimpleNamespace(
            title=title,
            transcript=transcript,
            speakers=speakers,
            additional_context=additional_context,
        )

    def test_get_prompt_returns_db_body_when_row_exists(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body="db body",
        )

        result = service.get_prompt("chat")

        self.assertEqual(result, "db body")

    def test_get_prompt_falls_back_to_default_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = None

        result = service.get_prompt("chat")

        self.assertEqual(result, DEFAULT_PROMPTS["chat"])

    def test_update_prompt_updates_existing_row(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing = self.make_row(task="chat", body="old body")
        db.query.return_value.filter.return_value.first.return_value = existing

        service.update_prompt("chat", "new body")

        self.assertEqual(existing.body, "new body")
        db.commit.assert_called_once()

    def test_update_prompt_inserts_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = None

        service.update_prompt("chat", "new body")

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_reset_to_default_restores_default_body(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing = self.make_row(task="summary", body="custom")
        db.query.return_value.filter.return_value.first.return_value = existing

        service.reset_to_default("summary")

        self.assertEqual(existing.body, DEFAULT_PROMPTS["summary"])

    def test_seed_defaults_inserts_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = None

        service.seed_defaults()

        self.assertEqual(db.add.call_count, len(DEFAULT_PROMPTS))
        db.commit.assert_called_once()

    def test_seed_defaults_preserves_existing_rows(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing_chat = self.make_row(task="chat", body="custom body")
        existing_summary = self.make_row(task="summary", body="custom summary")
        db.query.return_value.filter.return_value.first.side_effect = [
            existing_chat,
            existing_summary,
        ]

        service.seed_defaults()

        self.assertEqual(existing_chat.body, "custom body")
        self.assertEqual(existing_summary.body, "custom summary")
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_list_prompts_returns_all_rows(self):
        db = MagicMock()
        service = SystemPromptService(db)
        rows = [self.make_row("chat"), self.make_row("summary")]
        db.query.return_value.all.return_value = rows

        result = service.list_prompts()

        self.assertEqual(result, rows)

    def test_default_prompts_has_chat_and_summary_keys(self):
        self.assertIn("chat", DEFAULT_PROMPTS)
        self.assertIn("summary", DEFAULT_PROMPTS)

    def test_default_chat_prompt_uses_all_four_placeholders(self):
        chat_default = DEFAULT_PROMPTS["chat"]
        self.assertIn("{entry_title}", chat_default)
        self.assertIn("{transcript}", chat_default)
        self.assertIn("{speakers}", chat_default)
        self.assertIn("{additional_context}", chat_default)

    def test_render_prompt_substitutes_all_four_placeholders(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body=(
                "Title: {entry_title}\nSpeakers: {speakers}\n"
                "Context: {additional_context}\nTranscript: {transcript}"
            ),
        )

        result = service.render_prompt("chat", self.make_entry())

        self.assertEqual(
            result,
            "Title: Demo entry\nSpeakers: Alice, Bob\n"
            "Context: Standup notes\nTranscript: Hello world",
        )

    def test_render_prompt_substitutes_empty_strings_for_missing_metadata(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body="Speakers: {speakers}\nContext: {additional_context}",
        )

        result = service.render_prompt(
            "chat",
            self.make_entry(speakers="", additional_context=None),
        )

        self.assertEqual(result, "Speakers: \nContext: ")

    def test_render_prompt_strips_whitespace_from_metadata(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body="Speakers: {speakers}",
        )

        result = service.render_prompt(
            "chat",
            self.make_entry(speakers="  Alice  \n"),
        )

        self.assertEqual(result, "Speakers: Alice")

    def test_render_prompt_falls_back_to_raw_body_on_unknown_placeholder(self):
        db = MagicMock()
        service = SystemPromptService(db)
        raw_body = "Hello {foo}"
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body=raw_body,
        )

        result = service.render_prompt("chat", self.make_entry())

        self.assertEqual(result, raw_body)

    def test_render_prompt_falls_back_to_raw_body_on_malformed_template(self):
        db = MagicMock()
        service = SystemPromptService(db)
        raw_body = "Unbalanced {entry_title"
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body=raw_body,
        )

        result = service.render_prompt("chat", self.make_entry())

        self.assertEqual(result, raw_body)

    def test_render_prompt_returns_empty_string_when_body_is_empty(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat",
            body="",
        )

        result = service.render_prompt("chat", self.make_entry())

        self.assertEqual(result, "")

    def test_render_prompt_works_for_summary_task(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="summary",
            body="Summarize {entry_title}: {transcript}",
        )

        result = service.render_prompt("summary", self.make_entry())

        self.assertEqual(result, "Summarize Demo entry: Hello world")
