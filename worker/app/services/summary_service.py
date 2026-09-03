import asyncio

from groq import Groq
from loguru import logger

from app.core.config import settings, LLMProvider
from app.services.chunking_service import Chunk, split_transcript
from app.services.map_reduce_service import collapse_partials, map_chunks


class SummaryService:
    """Map-reduce transcript summarization for the ASR worker.

    Mirrors the provider initialization of the api ChatService (worker and
    api are separate images with duplicated modules by convention).
    """

    def __init__(self):
        self.provider = settings.llm_provider
        self.model = settings.llm_model

        if self.provider == LLMProvider.GROQ:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is required for Groq LLM service")
            self.client = Groq(api_key=settings.groq_api_key)
        elif self.provider == LLMProvider.CEREBRAS:
            if not settings.cerebras_api_key:
                raise ValueError(
                    "CEREBRAS_API_KEY is required for Cerebras LLM service",
                )
            from openai import OpenAI

            self.client = OpenAI(
                api_key=settings.cerebras_api_key,
                base_url="https://api.cerebras.ai/v1",
            )
        elif self.provider == LLMProvider.OLLAMA:
            from openai import OpenAI

            self.client = OpenAI(
                base_url=f"{settings.ollama_base_url}/v1",
                api_key="ollama",  # Ollama doesn't require a real API key
            )
            if settings.ollama_model:
                self.model = settings.ollama_model
        elif self.provider == LLMProvider.NEBIUS:
            if not settings.nebius_api_key:
                raise ValueError(
                    "NEBIUS_API_KEY is required for Nebius Token Factory LLM service",
                )
            from openai import OpenAI

            self.client = OpenAI(
                api_key=settings.nebius_api_key,
                base_url="https://api.tokenfactory.nebius.com/v1/",
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(
            f"Summary Service initialized with provider: {self.provider}, model: {self.model}",
        )

    async def _complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        completion = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
            top_p=0.9,
            stream=False,
        )
        return completion.choices[0].message.content.strip()

    async def _complete_map(self, messages: list[dict[str, str]]) -> str:
        return await self._complete(messages, max_tokens=512)

    async def generate_summary(
        self,
        transcript: str,
        title: str,
        speakers: str | None = None,
        additional_context: str | None = None,
    ) -> str:
        """Produce a complete summary of the transcript via map-reduce."""

        if not transcript or not transcript.strip():
            raise ValueError("Transcript is empty")

        metadata = self._format_metadata_section(speakers, additional_context)
        chunks = split_transcript(
            transcript,
            settings.summary_chunk_size,
            settings.summary_chunk_overlap,
        )

        if len(chunks) == 1:
            return await self._complete(
                self._build_single_messages(title, metadata, transcript),
            )

        logger.info(f"Map-reduce summary: {len(chunks)} chunks for '{title}'")
        partials = await map_chunks(
            self._complete_map,
            chunks,
            lambda c: self._build_map_messages(title, c, len(chunks)),
        )
        notes = [
            p if p is not None else f"[Section {i + 1} unavailable — extraction failed]"
            for i, p in enumerate(partials)
        ]
        collapsed = await collapse_partials(
            self._complete,
            notes,
            self._build_merge_messages,
        )
        return await self._complete(
            self._build_reduce_messages(title, metadata, collapsed),
        )

    @staticmethod
    def _format_metadata_section(
        speakers: str | None,
        additional_context: str | None,
    ) -> str:
        speakers = (speakers or "").strip()
        additional_context = (additional_context or "").strip()
        if not speakers and not additional_context:
            return ""
        sections = ["", "ENTRY METADATA:"]
        if speakers:
            sections.append(f"Speakers:\n{speakers}")
        if additional_context:
            sections.append(f"Additional Context:\n{additional_context}")
        sections.append("")
        return "\n".join(sections)

    @staticmethod
    def _build_single_messages(
        title: str,
        metadata: str,
        transcript: str,
    ) -> list[dict[str, str]]:
        prompt = f"""Please provide a concise summary of this transcript from "{title}":
{metadata}
TRANSCRIPT:
{transcript}

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

    @staticmethod
    def _build_map_messages(
        title: str,
        chunk: Chunk,
        total: int,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    f"You are analyzing section {chunk.index + 1} of {total} of a "
                    f'transcript from "{title}". Extract the key points, decisions, '
                    "action items and topics from this section. Be complete but "
                    "concise; do not invent content."
                ),
            },
            {"role": "user", "content": f"TRANSCRIPT SECTION:\n{chunk.text}"},
        ]

    @staticmethod
    def _build_merge_messages(text: str) -> list[dict[str, str]]:
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

    @staticmethod
    def _build_reduce_messages(
        title: str,
        metadata: str,
        notes: str,
    ) -> list[dict[str, str]]:
        prompt = f"""These are notes extracted from every section of a transcript from "{title}":
{metadata}
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
