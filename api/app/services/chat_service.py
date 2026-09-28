import httpx
from loguru import logger
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.entry import Entry


# Bound provider I/O below the MCP operation deadline; avoid hidden retry delays.
PROVIDER_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# The OpenAI SDK requires a non-None api_key (it raises OpenAIError otherwise),
# so keyless local servers get this placeholder instead; they ignore the header.
PLACEHOLDER_API_KEY = "not-needed"


def completion_text(completion) -> str:
    """Return the reply text, or explain why the endpoint sent none.

    Some OpenAI-compatible servers answer 200 with `content: null`, e.g. a
    reasoning model that spent its whole token budget on `reasoning_content`.
    """

    choice = completion.choices[0]
    content = choice.message.content
    if content:
        return content.strip()

    details = [f"finish_reason={choice.finish_reason}"]
    extra = choice.message.model_extra or {}
    if extra.get("reasoning_content") or extra.get("reasoning"):
        details.append("reply contained only reasoning")
    if choice.message.tool_calls:
        details.append("reply contained only tool calls")
    if choice.message.refusal:
        details.append(f"refusal={choice.message.refusal!r}")
    raise ValueError(f"LLM returned no text content ({', '.join(details)})")


class ChatService:
    """Chat and summarisation over any OpenAI-compatible chat completions API."""

    def __init__(self):
        if not settings.llm_base_url or not settings.llm_model:
            raise ValueError(
                "LLM_BASE_URL and LLM_MODEL are required for the chat service",
            )
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens
        self.extra_body = settings.llm_extra_body
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=settings.llm_api_key or PLACEHOLDER_API_KEY,
            timeout=PROVIDER_TIMEOUT,
            max_retries=0,
        )

        if not settings.llm_api_key:
            logger.warning(
                "No LLM_API_KEY is configured; calling "
                f"{self.base_url} without credentials. If this endpoint "
                "requires an API key, set LLM_API_KEY or requests will fail.",
            )

        logger.info(
            f"Chat Service initialized with endpoint: {self.base_url}, "
            f"model: {self.model}",
        )

    async def _complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        **params,
    ):
        """Call the endpoint with the configured token limit and extra body."""

        async with self.client:
            return await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens or max_tokens,
                extra_body=self.extra_body,
                **params,
            )

    async def chat_with_entry(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Generate a chat response about an entry using the configured LLM

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
        )

        try:
            # Call the OpenAI-compatible chat completions API
            completion = await self._complete(
                messages,
                max_tokens=1024,
                temperature=0.7,
                top_p=0.9,
                stream=False,
            )

            response = completion_text(completion)
            logger.info(
                f"Generated chat response for entry {entry.id} ({len(response)} chars)",
            )

            return response

        except Exception as e:
            logger.error(f"Error generating chat response: {str(e)}")
            raise Exception(f"Failed to generate chat response: {str(e)}")

    def _build_conversation_context(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build the conversation context for the chat model"""

        # System prompt with transcript context
        metadata_section = self._format_metadata_section(entry)

        system_prompt = f"""You are an AI assistant helping users analyze and discuss voice transcripts. You have access to a transcript from "{entry.title}".
{metadata_section}
TRANSCRIPT CONTENT:
{entry.transcript}

Your role:
- Answer questions about the transcript content
- Provide insights, summaries, and analysis
- Help identify key points, action items, and important information
- Be conversational and helpful
- If asked about something not in the transcript, politely mention the limitation
- Keep responses focused and relevant to the audio content

Guidelines:
- Be accurate and only reference information from the provided transcript
- Provide specific quotes when relevant
- Help with analysis like sentiment, key themes, action items, etc.
- Be concise but thorough in your responses
"""

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

    @staticmethod
    def _format_metadata_section(entry: Entry) -> str:
        """Render speakers and additional context as a system-prompt section.

        Returns an empty string when both fields are missing/blank, so the
        prompt stays clean for entries without metadata.
        """

        speakers = (getattr(entry, "speakers", None) or "").strip()
        additional_context = (getattr(entry, "additional_context", None) or "").strip()

        if not speakers and not additional_context:
            return ""

        sections = ["", "ENTRY METADATA:"]
        if speakers:
            sections.append(f"Speakers:\n{speakers}")
        if additional_context:
            sections.append(f"Additional Context:\n{additional_context}")
        sections.append("")
        return "\n".join(sections)

    async def generate_summary(self, entry: Entry) -> str:
        """Generate a summary of the entry transcript"""

        if not entry.transcript:
            raise ValueError("Entry must have a transcript to summarize")

        metadata_section = self._format_metadata_section(entry)

        summary_prompt = f"""Please provide a concise summary of this transcript from "{entry.title}":
{metadata_section}
TRANSCRIPT:
{entry.transcript}

Please provide:
1. A brief overview of the main topic/purpose
2. Key points discussed
3. Any action items or next steps mentioned
4. Overall outcome or conclusion

Keep the summary clear and structured."""

        try:
            completion = await self._complete(
                [
                    {
                        "role": "system",
                        "content": "You are an expert at summarizing voice transcripts. Provide clear, structured summaries.",
                    },
                    {"role": "user", "content": summary_prompt},
                ],
                max_tokens=512,
                temperature=0.3,
                top_p=0.9,
            )

            summary = completion_text(completion)
            logger.info(f"Generated summary for entry {entry.id}")

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    async def health_check(self) -> bool:
        """Check if LLM API is accessible for chat"""
        try:
            # Simple test call
            test_completion = await self._complete(
                [{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return bool(completion_text(test_completion))
        except Exception as e:
            logger.error(f"Chat service health check failed: {str(e)}")
            return False
