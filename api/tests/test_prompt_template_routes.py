import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import prompt_templates
from app.core import auth as auth_module
from app.core.auth import get_current_user
from app.core.config import AuthMode, Settings
from app.db.database import get_db

ADMIN = SimpleNamespace(email="ada@corp.com", display_name="Ada", is_system=False)
MEMBER = SimpleNamespace(email="bob@corp.com", display_name="Bob", is_system=False)
LOCAL_USER = SimpleNamespace(
    email="local@voicevault.local",
    display_name="Local User",
    is_system=True,
)

TEMPLATE_BODY = {
    "label": "Action items",
    "preview_text": "Extract action items",
    "body_markdown": "## Action Items\n- item",
    "sort_order": 10,
    "is_active": True,
}


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files from leaking into tests
    return Settings(_env_file=None, **overrides)


def make_template(**overrides) -> SimpleNamespace:
    now = datetime(2026, 4, 3, tzinfo=timezone.utc)
    base = {
        "id": uuid4(),
        "created_at": now,
        "updated_at": now,
        **TEMPLATE_BODY,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class PromptTemplateRouteTestCase(TestCase):
    """The router mounted on its own, with the auth and DB dependencies overridden.

    require_admin resolves get_current_user through FastAPI's dependency graph,
    so overriding get_current_user is enough to act as any user.
    """

    auth_mode = AuthMode.OIDC
    admin_emails = "ada@corp.com"

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(prompt_templates.router, prefix="/api/prompt-templates")
        self.app.dependency_overrides[get_db] = lambda: MagicMock()
        self.client = TestClient(self.app)

        service_patch = patch.object(prompt_templates, "PromptTemplateService")
        self.service = service_patch.start().return_value
        self.addCleanup(service_patch.stop)

        settings = make_settings(
            auth_mode=self.auth_mode,
            admin_emails=self.admin_emails,
        )
        settings_patch = patch.object(auth_module, "settings", settings)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    def act_as(self, user: SimpleNamespace) -> None:
        self.app.dependency_overrides[get_current_user] = lambda: user


class ListPromptTemplatesTests(PromptTemplateRouteTestCase):
    def test_admin_may_list_inactive_templates(self):
        self.act_as(ADMIN)
        self.service.list_templates.return_value = [make_template(is_active=False)]

        response = self.client.get(
            "/api/prompt-templates/",
            params={"active_only": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.service.list_templates.assert_called_once_with(active_only=False)

    def test_admin_active_only_flag_is_honoured(self):
        self.act_as(ADMIN)
        self.service.list_templates.return_value = []

        self.client.get("/api/prompt-templates/", params={"active_only": "true"})

        self.service.list_templates.assert_called_once_with(active_only=True)

    def test_non_admin_only_ever_sees_active_templates(self):
        # Inactive templates are configurator drafts; the flag is ignored for
        # everyone who cannot open the configurator.
        self.act_as(MEMBER)
        self.service.list_templates.return_value = [make_template()]

        response = self.client.get(
            "/api/prompt-templates/",
            params={"active_only": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["label"], "Action items")
        self.service.list_templates.assert_called_once_with(active_only=True)

    def test_non_admin_default_request_is_active_only(self):
        self.act_as(MEMBER)
        self.service.list_templates.return_value = []

        self.client.get("/api/prompt-templates/")

        self.service.list_templates.assert_called_once_with(active_only=True)


class CreatePromptTemplateTests(PromptTemplateRouteTestCase):
    def test_admin_may_create(self):
        self.act_as(ADMIN)
        self.service.create_template.return_value = make_template()

        response = self.client.post("/api/prompt-templates/", json=TEMPLATE_BODY)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "Action items")
        self.service.create_template.assert_called_once_with(**TEMPLATE_BODY)

    def test_non_admin_gets_404_and_nothing_is_written(self):
        self.act_as(MEMBER)

        response = self.client.post("/api/prompt-templates/", json=TEMPLATE_BODY)

        self.assertEqual(response.status_code, 404)
        self.service.create_template.assert_not_called()


class UpdatePromptTemplateTests(PromptTemplateRouteTestCase):
    def test_admin_may_update(self):
        self.act_as(ADMIN)
        template = make_template(label="Renamed")
        self.service.update_template.return_value = template

        response = self.client.put(
            f"/api/prompt-templates/{template.id}",
            json={"label": "Renamed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "Renamed")
        self.service.update_template.assert_called_once_with(
            template.id,
            label="Renamed",
        )

    def test_admin_gets_404_for_unknown_template(self):
        self.act_as(ADMIN)
        self.service.update_template.return_value = None

        response = self.client.put(
            f"/api/prompt-templates/{uuid4()}",
            json={"label": "x"},
        )

        self.assertEqual(response.status_code, 404)

    def test_non_admin_gets_404_and_nothing_is_written(self):
        self.act_as(MEMBER)

        response = self.client.put(
            f"/api/prompt-templates/{uuid4()}",
            json={"label": "x"},
        )

        self.assertEqual(response.status_code, 404)
        self.service.update_template.assert_not_called()


class DeletePromptTemplateTests(PromptTemplateRouteTestCase):
    def test_admin_may_delete(self):
        self.act_as(ADMIN)
        self.service.delete_template.return_value = True
        template_id = uuid4()

        response = self.client.delete(f"/api/prompt-templates/{template_id}")

        self.assertEqual(response.status_code, 200)
        self.service.delete_template.assert_called_once_with(template_id)

    def test_non_admin_gets_404_and_nothing_is_deleted(self):
        self.act_as(MEMBER)

        response = self.client.delete(f"/api/prompt-templates/{uuid4()}")

        self.assertEqual(response.status_code, 404)
        self.service.delete_template.assert_not_called()


class SharedLocalUserTests(PromptTemplateRouteTestCase):
    """none/token mode: the shared local user is the operator and keeps full access."""

    auth_mode = AuthMode.TOKEN
    admin_emails = ""

    def test_shared_local_user_may_configure_templates(self):
        self.act_as(LOCAL_USER)
        self.service.create_template.return_value = make_template()

        response = self.client.post("/api/prompt-templates/", json=TEMPLATE_BODY)

        self.assertEqual(response.status_code, 200)

    def test_shared_local_user_may_list_inactive_templates(self):
        self.act_as(LOCAL_USER)
        self.service.list_templates.return_value = []

        self.client.get("/api/prompt-templates/", params={"active_only": "false"})

        self.service.list_templates.assert_called_once_with(active_only=False)

    def test_leftover_oidc_user_cannot_configure_templates(self):
        # A database switched from oidc back to token still holds real user
        # rows; only the shared local account is the operator there.
        self.act_as(MEMBER)

        response = self.client.post("/api/prompt-templates/", json=TEMPLATE_BODY)

        self.assertEqual(response.status_code, 404)
        self.service.create_template.assert_not_called()
