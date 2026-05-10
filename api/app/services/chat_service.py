from groq import Groq
from loguru import logger

from app.core.config import settings, LLMProvider
from app.models.entry import Entry


class ChatService:
    def __init__(self):
        self.provider = settings.llm_provider
        self.model = settings.llm_model

        # Initialize client based on provider
        if self.provider == LLMProvider.GROQ:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is required for Groq LLM service")
            self.client = Groq(api_key=settings.groq_api_key)
        elif self.provider == LLMProvider.CEREBRAS:
            if not settings.cerebras_api_key:
                raise ValueError(
                    "CEREBRAS_API_KEY is required for Cerebras LLM service",
                )
            # Cerebras uses OpenAI-compatible API
            from openai import OpenAI

            self.client = OpenAI(
                api_key=settings.cerebras_api_key,
                base_url="https://api.cerebras.ai/v1",
            )
        elif self.provider == LLMProvider.OLLAMA:
            # Ollama uses OpenAI-compatible API
            from openai import OpenAI

            self.client = OpenAI(
                base_url=f"{settings.ollama_base_url}/v1",
                api_key="ollama",  # Ollama doesn't require a real API key
            )
            # Override model with Ollama-specific model
            if settings.ollama_model:
                self.model = settings.ollama_model
        elif self.provider == LLMProvider.NEBIUS:
            if not settings.nebius_api_key:
                raise ValueError(
                    "NEBIUS_API_KEY is required for Nebius Token Factory LLM service",
                )
            # Nebius uses OpenAI-compatible API
            from openai import OpenAI

            self.client = OpenAI(
                api_key=settings.nebius_api_key,
                base_url="https://api.tokenfactory.nebius.com/v1/",
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(
            f"Chat Service initialized with provider: {self.provider}, model: {self.model}",
        )

    async def chat_with_entry(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
    ) -> str:
        """
        Generate a chat response about an entry using Groq Llama 3.1

        Args:
            entry: The entry to chat about
            user_message: The user's message/question
            conversation_history: Previous messages in the conversation

        Returns:
            AI response as string
        """

        if not entry.transcript:
            raise ValueError("Entry must have a transcript to chat about")

        # Build conversation context
        messages = self._build_conversation_context(
            entry,
            user_message,
            conversation_history,
            system_prompt,
        )

        try:
            # Call LLM API (supports Groq and Cerebras)
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
                top_p=0.9,
                stream=False,
            )

            response = completion.choices[0].message.content
            logger.info(
                f"Generated chat response for entry {entry.id} ({len(response)} chars)",
            )

            return response.strip()

        except Exception as e:
            logger.error(f"Error generating chat response: {str(e)}")
            raise Exception(f"Failed to generate chat response: {str(e)}")

    def _build_conversation_context(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
    ) -> list[dict[str, str]]:
        """Build the conversation context for the LLM"""
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append(
                        {
                            "role": msg["role"],
                            "content": msg["content"],
                        },
                    )

        # Add current user message
        messages.append(
            {
                "role": "user",
                "content": user_message,
            },
        )

        return messages

    async def generate_summary(self, entry: Entry, system_prompt: str = "") -> str:
        """Generate a summary of the entry transcript"""

        if not entry.transcript:
            raise ValueError("Entry must have a transcript to summarize")

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": entry.transcript},
                ],
                max_tokens=512,
                temperature=0.3,
                top_p=0.9,
            )

            summary = completion.choices[0].message.content
            logger.info(f"Generated summary for entry {entry.id}")

            return summary.strip()

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def health_check(self) -> bool:
        """Check if LLM API is accessible for chat"""
        try:
            # Simple test call
            test_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return bool(test_completion.choices[0].message.content)
        except Exception as e:
            logger.error(f"Chat service health check failed: {str(e)}")
            return False
