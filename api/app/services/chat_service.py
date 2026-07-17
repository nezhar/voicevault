import asyncio

from groq import Groq
from loguru import logger

from app.core.config import settings, LLMProvider
from app.models.entry import Entry
from app.services.chunking_service import Chunk, split_transcript
from app.services.map_reduce_service import collapse_partials, map_chunks


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

    async def _complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """Run one completion; the Groq/OpenAI clients are sync, so hop to a
        thread to keep map calls truly parallel."""
        completion = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
            stream=False,
        )
        return completion.choices[0].message.content.strip()

    async def _complete_map(self, messages: list[dict[str, str]]) -> str:
        """Map-stage completion: shorter output budget for chunk extraction."""
        return await self._complete(messages, max_tokens=512)

    async def chat_with_entry(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
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
    ) -> list[dict[str, str]]:
        """Build the conversation context for the Llama model"""

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
        """Generate a complete summary via map-reduce over transcript chunks."""

        if not entry.transcript:
            raise ValueError("Entry must have a transcript to summarize")

        chunks = split_transcript(
            entry.transcript,
            settings.summary_chunk_size,
            settings.summary_chunk_overlap,
        )

        try:
            if len(chunks) == 1:
                summary = await self._complete(
                    self._build_summary_single_messages(entry),
                    max_tokens=1024,
                )
            else:
                logger.info(
                    f"Map-reduce summary for entry {entry.id}: {len(chunks)} chunks",
                )
                partials = await map_chunks(
                    self._complete_map,
                    chunks,
                    lambda c: self._build_summary_map_messages(entry, c, len(chunks)),
                )
                notes = [
                    p
                    if p is not None
                    else f"[Section {i + 1} unavailable — extraction failed]"
                    for i, p in enumerate(partials)
                ]
                collapsed = await collapse_partials(
                    self._complete,
                    notes,
                    self._build_summary_merge_messages,
                )
                summary = await self._complete(
                    self._build_summary_reduce_messages(entry, collapsed),
                    max_tokens=1024,
                )

            logger.info(f"Generated summary for entry {entry.id}")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def _build_summary_single_messages(self, entry: Entry) -> list[dict[str, str]]:
        metadata_section = self._format_metadata_section(entry)
        prompt = f"""Please provide a concise summary of this transcript from "{entry.title}":
{metadata_section}
TRANSCRIPT:
{entry.transcript}

Please provide:
1. A brief overview of the main topic/purpose
2. Key points discussed
3. Any action items or next steps mentioned
4. Overall outcome or conclusion

Keep the summary clear and structured."""
        return [
            {
                "role": "system",
                "content": "You are an expert at summarizing voice transcripts. Provide clear, structured summaries.",
            },
            {"role": "user", "content": prompt},
        ]

    def _build_summary_map_messages(
        self,
        entry: Entry,
        chunk: Chunk,
        total: int,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    f"You are analyzing section {chunk.index + 1} of {total} of a "
                    f'transcript from "{entry.title}". Extract the key points, '
                    "decisions, action items and topics from this section. Be "
                    "complete but concise; do not invent content."
                ),
            },
            {"role": "user", "content": f"TRANSCRIPT SECTION:\n{chunk.text}"},
        ]

    def _build_summary_merge_messages(self, text: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Merge these section notes from one transcript into a single "
                    "consolidated set of notes. Keep every key point, decision, "
                    "action item and topic; deduplicate overlapping content."
                ),
            },
            {"role": "user", "content": text},
        ]

    def _build_summary_reduce_messages(
        self,
        entry: Entry,
        notes: str,
    ) -> list[dict[str, str]]:
        metadata_section = self._format_metadata_section(entry)
        prompt = f"""These are notes extracted from every section of a transcript from "{entry.title}":
{metadata_section}
SECTION NOTES:
{notes}

Synthesize one complete summary covering the entire recording:
1. A brief overview of the main topic/purpose
2. Key points discussed
3. Any action items or next steps mentioned
4. Overall outcome or conclusion

Keep the summary clear and structured. If a section is marked unavailable, mention that a part of the recording could not be analyzed."""
        return [
            {
                "role": "system",
                "content": "You are an expert at summarizing voice transcripts. Provide clear, structured summaries.",
            },
            {"role": "user", "content": prompt},
        ]

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
