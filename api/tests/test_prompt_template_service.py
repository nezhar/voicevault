import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.prompt_template_service import DEFAULT_PROMPT_TEMPLATES, PromptTemplateService


class PromptTemplateServiceTests(TestCase):
    def make_template(self, **overrides):
        base = {
            "id": "template-1",
            "label": "Action items",
            "preview_text": "Extract action items",
            "body_markdown": "## Action Items\n- item",
            "sort_order": 10,
            "is_active": True,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_lists_templates_by_sort_order(self):
        db = MagicMock()
        service = PromptTemplateService(db)
        query = db.query.return_value
        ordered = query.order_by.return_value
        ordered.all.return_value = [
            self.make_template(sort_order=10),
            self.make_template(id="template-2", sort_order=20),
        ]

        templates = service.list_templates()

        self.assertEqual([template.sort_order for template in templates], [10, 20])

    def test_creates_template(self):
        db = MagicMock()
        service = PromptTemplateService(db)
        template = service.create_template(
            label="Action items",
            preview_text="Extract action items",
            body_markdown="## Action Items\n- item",
            sort_order=10,
            is_active=True,
        )

        self.assertEqual(template.label, "Action items")
        self.assertEqual(template.sort_order, 10)
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(template)

    def test_seeds_defaults_only_when_empty(self):
        db = MagicMock()
        service = PromptTemplateService(db)
        query = db.query.return_value
        query.count.side_effect = [0, 2]

        with patch.object(service.db, "add_all") as add_all_mock:
            first = service.seed_defaults_if_empty()
            second = service.seed_defaults_if_empty()

        self.assertEqual(first, len(DEFAULT_PROMPT_TEMPLATES))
        self.assertEqual(second, 0)
        add_all_mock.assert_called_once()
        db.commit.assert_called_once()
