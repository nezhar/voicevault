import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import database


class EntrySchemaRepairTests(TestCase):
    @patch("app.db.database.text", side_effect=lambda statement: statement)
    @patch("app.db.database.inspect")
    def test_adds_archived_column_when_missing(self, inspect_mock, text_mock):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["entries"]
        inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "title"},
            {"name": "speakers"},
            {"name": "additional_context"},
        ]
        inspect_mock.return_value = inspector

        connection = MagicMock()
        begin_context = MagicMock()
        begin_context.__enter__.return_value = connection
        begin_context.__exit__.return_value = None

        with patch.object(database.engine, "begin", return_value=begin_context):
            database.ensure_entry_schema()

        text_mock.assert_called_once_with(
            "ALTER TABLE entries ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false",
        )
        connection.execute.assert_called_once()

    @patch("app.db.database.text", side_effect=lambda statement: statement)
    @patch("app.db.database.inspect")
    def test_adds_metadata_columns_when_missing(self, inspect_mock, text_mock):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["entries"]
        inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "title"},
            {"name": "archived"},
        ]
        inspect_mock.return_value = inspector

        connection = MagicMock()
        begin_context = MagicMock()
        begin_context.__enter__.return_value = connection
        begin_context.__exit__.return_value = None

        with patch.object(database.engine, "begin", return_value=begin_context):
            database.ensure_entry_schema()

        statements = [call.args[0] for call in text_mock.call_args_list]
        self.assertIn(
            "ALTER TABLE entries ADD COLUMN speakers TEXT",
            statements,
        )
        self.assertIn(
            "ALTER TABLE entries ADD COLUMN additional_context TEXT",
            statements,
        )
        self.assertEqual(connection.execute.call_count, 2)

    @patch("app.db.database.inspect")
    def test_skips_when_all_columns_exist(self, inspect_mock):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["entries"]
        inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "archived"},
            {"name": "speakers"},
            {"name": "additional_context"},
        ]
        inspect_mock.return_value = inspector

        begin_mock = MagicMock()

        with patch.object(database.engine, "begin", begin_mock):
            database.ensure_entry_schema()

        begin_mock.assert_not_called()
