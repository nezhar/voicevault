"""Exercise real async provider clients without external network calls."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from groq import AsyncGroq
from openai import AsyncOpenAI

from app.core.config import LLMProvider, settings
from app.services.chat_service import ChatService


class ChatServiceTests(IsolatedAsyncioTestCase):
    async def test_all_providers_await_requests_and_close_clients(self):
        entry = SimpleNamespace(id="fixture", title="Meeting", transcript="Notes")
        for provider in LLMProvider:
            for operation in ("chat", "summary", "health"):
                with self.subTest(provider=provider, operation=operation):
                    requests = []

                    async def respond(request):
                        requests.append(request)
                        return httpx.Response(
                            200,
                            json={
                                "id": "completion",
                                "object": "chat.completion",
                                "created": 0,
                                "model": "test-model",
                                "choices": [
                                    {
                                        "index": 0,
                                        "finish_reason": "stop",
                                        "message": {
                                            "role": "assistant",
                                            "content": " Answer ",
                                        },
                                    },
                                ],
                            },
                        )

                    def groq_client(**kwargs):
                        return AsyncGroq(
                            **kwargs,
                            http_client=httpx.AsyncClient(
                                transport=httpx.MockTransport(respond),
                            ),
                        )

                    def openai_client(**kwargs):
                        return AsyncOpenAI(
                            **kwargs,
                            http_client=httpx.AsyncClient(
                                transport=httpx.MockTransport(respond),
                            ),
                        )

                    with (
                        patch.object(settings, "llm_provider", provider),
                        patch.object(settings, "groq_api_key", "test-key"),
                        patch.object(settings, "cerebras_api_key", "test-key"),
                        patch.object(settings, "nebius_api_key", "test-key"),
                        patch(
                            "app.services.chat_service.AsyncGroq",
                            side_effect=groq_client,
                        ),
                        patch("openai.AsyncOpenAI", side_effect=openai_client),
                    ):
                        service = ChatService()
                        if operation == "chat":
                            self.assertEqual(
                                await service.chat_with_entry(entry, "Explain"),
                                "Answer",
                            )
                        elif operation == "summary":
                            self.assertEqual(
                                await service.generate_summary(entry),
                                "Answer",
                            )
                        else:
                            self.assertTrue(await service.health_check())
                        self.assertTrue(service.client.is_closed())
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(requests[0].extensions["timeout"]["read"], 120.0)
                    self.assertEqual(requests[0].extensions["timeout"]["connect"], 10.0)
