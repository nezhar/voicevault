"""Exercise the real async OpenAI client without external network calls."""

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.chat_service import PLACEHOLDER_API_KEY, ChatService

BASE_URL = "http://llm.test/v1"
ENTRY = SimpleNamespace(id="fixture", title="Meeting", transcript="Notes")

COMPLETION = {
    "id": "completion",
    "object": "chat.completion",
    "created": 0,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": " Answer "},
        },
    ],
}


def make_service(
    requests: list,
    response: httpx.Response | None = None,
    **overrides,
) -> ChatService:
    """Build a ChatService whose HTTP layer records into `requests`.

    By default the mock transport returns a 200 with `COMPLETION`; pass
    `response` to have it return something else instead (e.g. an error).
    """

    async def respond(request):
        requests.append(request)
        return (
            response if response is not None else httpx.Response(200, json=COMPLETION)
        )

    def openai_client(**kwargs):
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )

    values = {"llm_base_url": BASE_URL, "llm_model": "test-model", "llm_api_key": None}
    values.update(overrides)
    with (
        patch.multiple(settings, **values),
        patch("app.services.chat_service.AsyncOpenAI", side_effect=openai_client),
    ):
        return ChatService()


class ChatServiceTests(IsolatedAsyncioTestCase):
    async def test_operations_hit_configured_endpoint_and_close_client(self):
        for operation in ("chat", "summary", "health"):
            with self.subTest(operation=operation):
                requests = []
                service = make_service(requests)
                if operation == "chat":
                    self.assertEqual(
                        await service.chat_with_entry(ENTRY, "Explain"),
                        "Answer",
                    )
                elif operation == "summary":
                    self.assertEqual(await service.generate_summary(ENTRY), "Answer")
                else:
                    self.assertTrue(await service.health_check())
                self.assertTrue(service.client.is_closed())
                self.assertEqual(len(requests), 1)
                request = requests[0]
                self.assertEqual(str(request.url), f"{BASE_URL}/chat/completions")
                self.assertEqual(json.loads(request.content)["model"], "test-model")
                self.assertEqual(request.extensions["timeout"]["read"], 120.0)
                self.assertEqual(request.extensions["timeout"]["connect"], 10.0)

    async def test_unset_api_key_sends_placeholder_bearer(self):
        requests = []
        service = make_service(requests, llm_api_key=None)
        await service.health_check()
        self.assertEqual(
            requests[0].headers["authorization"],
            f"Bearer {PLACEHOLDER_API_KEY}",
        )

    async def test_configured_api_key_is_sent_as_bearer(self):
        requests = []
        service = make_service(requests, llm_api_key="secret")
        await service.health_check()
        self.assertEqual(requests[0].headers["authorization"], "Bearer secret")

    async def test_provider_error_response_is_wrapped_without_leaking_api_key(self):
        requests = []
        api_key = "sk-should-not-leak"
        service = make_service(
            requests,
            response=httpx.Response(
                401,
                json={
                    "error": {
                        "message": "Invalid API key",
                        "type": "invalid_request_error",
                    },
                },
            ),
            llm_api_key=api_key,
        )
        with self.assertRaises(Exception) as cm:
            await service.chat_with_entry(ENTRY, "Explain")

        self.assertTrue(
            str(cm.exception).startswith("Failed to generate chat response: "),
        )
        self.assertNotIn(api_key, str(cm.exception))

    def test_requires_base_url_and_model(self):
        for missing in ("llm_base_url", "llm_model"):
            with self.subTest(missing=missing):
                values = {"llm_base_url": BASE_URL, "llm_model": "test-model"}
                values[missing] = None
                with patch.multiple(settings, **values):
                    with self.assertRaises(ValueError):
                        ChatService()
