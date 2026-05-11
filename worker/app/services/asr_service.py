import os
import asyncio
import subprocess
from typing import Any
from groq import Groq
import httpx
from loguru import logger

from app.core.config import settings, ASRProvider
from app.services.s3_service import S3Service
from app.services.audio_conversion_service import AudioConversionService
from app.services.audio_chunking_service import AudioChunkingService


class ASRService:
    def __init__(self):
        self.provider = settings.asr_provider
        self.model = settings.asr_model
        self.client = None
        self.whisper_asr_url = None

        # Initialize client based on provider
        if self.provider == ASRProvider.GROQ:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is required for Groq ASR service")
            self.client = Groq(api_key=settings.groq_api_key)
        elif self.provider == ASRProvider.WHISPER_ASR:
            self.whisper_asr_url = settings.whisper_asr_url
            logger.info(f"Using whisper-asr-webservice at {self.whisper_asr_url}")
        else:
            raise ValueError(f"Unsupported ASR provider: {self.provider}")

        logger.info(
            f"ASR Service initialized with provider: {self.provider}, model: {self.model}",
        )
        self._s3_service = None
        self._audio_conversion_service = None
        self._audio_chunking_service = None

    @property
    def s3_service(self):
        """Lazy initialization of S3 service to avoid async context issues"""
        if self._s3_service is None:
            self._s3_service = S3Service()
        return self._s3_service

    @property
    def audio_conversion_service(self):
        """Lazy initialization of audio conversion service"""
        if self._audio_conversion_service is None:
            self._audio_conversion_service = AudioConversionService()
        return self._audio_conversion_service

    @property
    def audio_chunking_service(self):
        """Lazy initialization of audio chunking service"""
        if self._audio_chunking_service is None:
            self._audio_chunking_service = AudioChunkingService()
        return self._audio_chunking_service

    async def transcribe_file(
        self,
        s3_key: str,
        entry_id: str,
    ) -> tuple[
        bool,
        str | None,
        list[dict[str, Any]] | None,
        list[dict[str, Any]] | None,
        str | None,
    ]:
        """
        Transcribe audio/video file from S3 using the configured ASR provider.
        Handles large files by chunking them into smaller pieces.

        Returns:
            Tuple[success, transcript_text, words, segments, error_message]

            `words` is a list of {"word", "start", "end"} dicts and `segments`
            is a list of {"text", "start", "end"} dicts (both in seconds with
            millisecond precision). Either may be None if the provider did
            not return that granularity.
        """

        # Check if file exists in S3
        if not self.s3_service.file_exists(s3_key):
            error_msg = f"File not found in S3: {s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg

        # All files are now MP3 format (uploads are original, downloads are converted in download service)
        transcription_s3_key = s3_key
        logger.info(
            f"Entry {entry_id}: Using file for transcription (already in MP3 format): {s3_key}",
        )

        # Verify the file exists and get its info
        if not self.s3_service.file_exists(transcription_s3_key):
            error_msg = f"File not found in S3: {transcription_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg

        # Get file info for transcription
        file_info = self.s3_service.get_file_info(transcription_s3_key)
        file_size = file_info.get("size", 0) if file_info else 0

        logger.info(
            f"Entry {entry_id}: File size: {file_size} bytes ({file_size / (1024 * 1024):.1f} MB)",
        )
        logger.info(
            f"Entry {entry_id}: Groq chunk size limit: {settings.max_file_size} bytes ({settings.max_file_size / (1024 * 1024):.1f} MB)",
        )

        # Download file to temporary location
        temp_file_path = self.s3_service.create_temp_download(transcription_s3_key)
        if not temp_file_path:
            error_msg = f"Failed to download file from S3: {transcription_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg

        try:
            # Whisper ASR webservice has no inherent file limit, so skip chunking
            if self.provider == ASRProvider.WHISPER_ASR:
                logger.info(
                    f"Entry {entry_id}: Using whisper-asr-webservice (no chunking needed)",
                )
                return await self._transcribe_single_file(temp_file_path, entry_id)

            # Use the actual file size that will be sent to Groq for chunking decision
            if file_size > settings.max_file_size:
                logger.info(
                    f"Entry {entry_id}: File size ({file_size}) exceeds Groq limit ({settings.max_file_size}), using chunked transcription",
                )
                return await self._transcribe_chunked_file(temp_file_path, entry_id)
            else:
                logger.info(
                    f"Entry {entry_id}: File size ({file_size}) is within Groq limits, using direct single API call",
                )
                return await self._transcribe_single_file(temp_file_path, entry_id)

        except Exception as e:
            error_msg = f"Transcription error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg
        finally:
            # Clean up temporary file
            self.s3_service.cleanup_temp_file(temp_file_path)

    async def _transcribe_single_file(
        self,
        temp_file_path: str,
        entry_id: str,
    ) -> tuple[
        bool,
        str | None,
        list[dict[str, Any]] | None,
        list[dict[str, Any]] | None,
        str | None,
    ]:
        """Transcribe a single file that fits within provider limits"""
        try:
            # Safety check: Verify file size is within Groq limits (only for Groq provider)
            if os.path.exists(temp_file_path):
                file_size = os.path.getsize(temp_file_path)
                if (
                    self.provider == ASRProvider.GROQ
                    and file_size > settings.max_file_size
                ):
                    logger.warning(
                        f"Entry {entry_id}: File size {file_size} exceeds Groq limit {settings.max_file_size}, falling back to chunking",
                    )
                    return await self._transcribe_chunked_file(temp_file_path, entry_id)
                logger.info(f"Entry {entry_id}: File size {file_size} bytes")

            logger.info(f"Entry {entry_id}: Starting single file transcription")

            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            transcript, words, segments = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                temp_file_path,
                None,
                entry_id,
            )

            if transcript:
                logger.info(
                    f"Entry {entry_id}: Single file transcription completed "
                    f"({len(transcript)} characters, {len(words) if words else 0} words, "
                    f"{len(segments) if segments else 0} segments)",
                )
                return True, transcript, words, segments, None
            else:
                error_msg = "Empty transcript returned"
                logger.warning(f"Entry {entry_id}: {error_msg}")
                return False, None, None, None, error_msg

        except Exception as e:
            error_msg = f"Single file transcription error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg

    async def _transcribe_chunked_file(
        self,
        temp_file_path: str,
        entry_id: str,
    ) -> tuple[
        bool,
        str | None,
        list[dict[str, Any]] | None,
        list[dict[str, Any]] | None,
        str | None,
    ]:
        """Transcribe a large file by splitting it into chunks"""
        chunk_paths = []
        cleanup_chunks = True
        try:
            logger.info(f"Entry {entry_id}: Starting chunked transcription")

            # Split the file into chunks
            (
                chunking_success,
                chunk_paths,
                chunking_error,
            ) = await self.audio_chunking_service.chunk_audio_file(
                temp_file_path,
                entry_id,
            )

            if not chunking_success:
                return (
                    False,
                    None,
                    None,
                    None,
                    f"Failed to chunk audio file: {chunking_error}",
                )

            # Check if chunking was actually needed (single file returned)
            if len(chunk_paths) == 1 and chunk_paths[0] == temp_file_path:
                logger.info(
                    f"Entry {entry_id}: File doesn't need chunking, processing as single file",
                )
                cleanup_chunks = False  # Don't clean up the original file
                return await self._transcribe_single_file(temp_file_path, entry_id)

            logger.info(
                f"Entry {entry_id}: Processing {len(chunk_paths)} chunks sequentially (multiple API calls to respect size limits)",
            )

            # Each chunk's timestamps are reset to 0 by ffmpeg, so we shift by
            # the cumulative duration of preceding chunks to recover absolute
            # positions in the original audio.
            transcripts: list[str] = []
            all_words: list[dict[str, Any]] = []
            all_segments: list[dict[str, Any]] = []
            cumulative_offset = 0.0
            any_words_seen = False
            any_segments_seen = False

            for i, chunk_path in enumerate(chunk_paths):
                try:
                    chunk_size = os.path.getsize(chunk_path)
                    logger.info(
                        f"Entry {entry_id}: Transcribing chunk {i + 1}/{len(chunk_paths)} (size: {chunk_size} bytes, limit: {settings.max_file_size} bytes)",
                    )

                    chunk_duration = await self._probe_audio_duration(chunk_path)

                    # Verify chunk size is within limits
                    if chunk_size > settings.max_file_size:
                        logger.error(
                            f"Entry {entry_id}: Chunk {i + 1} is still too large: {chunk_size} bytes, skipping",
                        )
                        if chunk_duration is not None:
                            cumulative_offset += chunk_duration
                        continue

                    logger.info(
                        f"Entry {entry_id}: Sending chunk {i + 1}/{len(chunk_paths)} to Groq API (sequential processing)",
                    )

                    # Run transcription in executor - SEQUENTIAL, not parallel
                    loop = asyncio.get_event_loop()
                    (
                        chunk_transcript,
                        chunk_words,
                        chunk_segments,
                    ) = await loop.run_in_executor(
                        None,
                        self._transcribe_sync,
                        chunk_path,
                        None,
                        f"{entry_id}_chunk_{i + 1}",
                    )

                    if chunk_transcript:
                        transcripts.append(chunk_transcript.strip())
                        logger.info(
                            f"Entry {entry_id}: Chunk {i + 1}/{len(chunk_paths)} transcribed successfully "
                            f"({len(chunk_transcript)} characters, {len(chunk_words) if chunk_words else 0} words, "
                            f"{len(chunk_segments) if chunk_segments else 0} segments)",
                        )
                    else:
                        logger.warning(
                            f"Entry {entry_id}: Chunk {i + 1}/{len(chunk_paths)} returned empty transcript",
                        )

                    if chunk_words:
                        any_words_seen = True
                        for word in chunk_words:
                            all_words.append(
                                {
                                    "word": word["word"],
                                    "start": round(
                                        word["start"] + cumulative_offset,
                                        3,
                                    ),
                                    "end": round(word["end"] + cumulative_offset, 3),
                                },
                            )

                    if chunk_segments:
                        any_segments_seen = True
                        for segment in chunk_segments:
                            all_segments.append(
                                {
                                    "text": segment["text"],
                                    "start": round(
                                        segment["start"] + cumulative_offset,
                                        3,
                                    ),
                                    "end": round(segment["end"] + cumulative_offset, 3),
                                },
                            )

                    if chunk_duration is not None:
                        cumulative_offset += chunk_duration
                    elif chunk_words:
                        # Fallback: advance offset to the last word's end so subsequent
                        # chunks aren't stacked on top of this one if duration probing failed.
                        cumulative_offset = max(cumulative_offset, all_words[-1]["end"])
                    elif chunk_segments:
                        cumulative_offset = max(
                            cumulative_offset,
                            all_segments[-1]["end"],
                        )

                    # Small delay between requests to avoid rate limiting
                    if i < len(chunk_paths) - 1:  # Don't delay after the last chunk
                        await asyncio.sleep(0.5)  # 500ms delay between API calls

                except Exception as e:
                    logger.error(
                        f"Entry {entry_id}: Error transcribing chunk {i + 1}: {str(e)}",
                    )
                    # Continue with other chunks even if one fails
                    continue

            if not transcripts:
                return (
                    False,
                    None,
                    None,
                    None,
                    "No chunks were successfully transcribed",
                )

            # Combine transcripts with paragraph breaks for readability
            combined_transcript = "\n\n".join(transcripts)
            combined_words = all_words if any_words_seen else None
            combined_segments = all_segments if any_segments_seen else None

            logger.info(
                f"Entry {entry_id}: Chunked transcription completed - {len(transcripts)} successful chunks, "
                f"{len(combined_transcript)} total characters, "
                f"{len(combined_words) if combined_words else 0} words, "
                f"{len(combined_segments) if combined_segments else 0} segments",
            )
            logger.info(
                f"Entry {entry_id}: Combined transcript preview: {combined_transcript[:200]}...",
            )
            return True, combined_transcript, combined_words, combined_segments, None

        except Exception as e:
            error_msg = f"Chunked transcription error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, None, None, error_msg
        finally:
            # Clean up chunk files (but not the original file if it wasn't actually chunked)
            if chunk_paths and cleanup_chunks:
                self.audio_chunking_service.cleanup_chunks(chunk_paths)

    @staticmethod
    async def _probe_audio_duration(file_path: str) -> float | None:
        """Return audio duration in seconds via ffprobe, or None on failure."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "quiet",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        file_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"ffprobe duration probe failed for {file_path}: {e}")
        return None

    def _transcribe_sync(
        self,
        file_path: str,
        s3_key: str = None,
        entry_id: str = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        """Synchronous transcription returning (text, words, segments).

        Each list element is a dict with timestamps in seconds rounded to
        millisecond precision. words have shape {"word", "start", "end"} and
        segments have shape {"text", "start", "end"}. Either list may be None
        if the provider didn't return that granularity.
        """
        if self.provider == ASRProvider.GROQ:
            return self._transcribe_groq_sync(file_path, entry_id)
        elif self.provider == ASRProvider.WHISPER_ASR:
            return self._transcribe_whisper_asr_sync(file_path, entry_id)
        else:
            raise ValueError(f"Unsupported ASR provider: {self.provider}")

    @staticmethod
    def _normalize_word_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a single word entry from a provider into our canonical shape."""
        token = raw.get("word") if "word" in raw else raw.get("text")
        if token is None:
            return None
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            return None
        # Round to millisecond precision for consistency across providers
        return {
            "word": str(token),
            "start": round(start, 3),
            "end": round(end, 3),
        }

    @staticmethod
    def _normalize_segment_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a segment entry into {"text", "start", "end"}."""
        text = raw.get("text")
        if text is None:
            return None
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            return None
        cleaned = str(text).strip()
        if not cleaned:
            return None
        return {
            "text": cleaned,
            "start": round(start, 3),
            "end": round(end, 3),
        }

    def _transcribe_groq_sync(
        self,
        file_path: str,
        entry_id: str = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        """Synchronous Groq transcription with word-level timestamps"""
        try:
            # File is already in Groq-compatible format (MP3) after conversion
            file_size = os.path.getsize(file_path)
            logger.info(
                f"Entry {entry_id or 'unknown'}: Sending file to Groq - path: {file_path}, size: {file_size} bytes",
            )

            # Check the actual file type using the file command (if available)
            try:
                import shutil

                # Check if 'file' command is available
                if shutil.which("file"):
                    result = subprocess.run(
                        ["file", "-b", "--mime-type", file_path],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        detected_type = result.stdout.strip()
                        logger.info(
                            f"Entry {entry_id or 'unknown'}: Detected file type: {detected_type}",
                        )
                    else:
                        logger.debug(
                            f"Entry {entry_id or 'unknown'}: Could not detect file type with 'file' command",
                        )
                else:
                    logger.debug(
                        f"Entry {entry_id or 'unknown'}: 'file' command not available, proceeding with MP3 assumption",
                    )
            except Exception as e:
                logger.debug(
                    f"Entry {entry_id or 'unknown'}: File type detection skipped: {str(e)}",
                )

            with open(file_path, "rb") as audio_file:
                # Create a file-like object with proper filename for Groq
                # Groq needs the filename to detect the format properly
                file_name = f"audio_{entry_id or 'unknown'}.mp3"
                logger.info(
                    f"Entry {entry_id or 'unknown'}: Sending to Groq with filename: {file_name}",
                )

                # Request verbose_json with both word- and segment-level
                # timestamps so we can fall back to segments when callers don't
                # need or have word-level granularity.
                transcription = self.client.audio.transcriptions.create(
                    file=(file_name, audio_file, "audio/mpeg"),
                    model=self.model,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                    temperature=0.0,
                )

                text: str | None = None
                raw_words: list[Any] = []
                raw_segments: list[Any] = []

                if hasattr(transcription, "text"):
                    text = transcription.text.strip() if transcription.text else None
                    raw_words = list(getattr(transcription, "words", None) or [])
                    raw_segments = list(getattr(transcription, "segments", None) or [])
                elif isinstance(transcription, dict):
                    text = (transcription.get("text") or "").strip() or None
                    raw_words = list(transcription.get("words") or [])
                    raw_segments = list(transcription.get("segments") or [])
                elif isinstance(transcription, str):
                    text = transcription.strip() or None

                def _coerce(item: Any) -> dict[str, Any] | None:
                    if hasattr(item, "model_dump"):
                        return item.model_dump()
                    if hasattr(item, "dict"):
                        return item.dict()
                    return item if isinstance(item, dict) else None

                normalized_words: list[dict[str, Any]] = []
                for w in raw_words:
                    coerced = _coerce(w)
                    if coerced is None:
                        continue
                    norm = self._normalize_word_entry(coerced)
                    if norm is not None:
                        normalized_words.append(norm)

                normalized_segments: list[dict[str, Any]] = []
                for s in raw_segments:
                    coerced = _coerce(s)
                    if coerced is None:
                        continue
                    norm = self._normalize_segment_entry(coerced)
                    if norm is not None:
                        normalized_segments.append(norm)

                return text, (normalized_words or None), (normalized_segments or None)

        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            raise

    def _transcribe_whisper_asr_sync(
        self,
        file_path: str,
        entry_id: str = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        """Synchronous whisper-asr-webservice transcription with word-level timestamps"""
        try:
            file_size = os.path.getsize(file_path)
            logger.info(
                f"Entry {entry_id or 'unknown'}: Sending file to whisper-asr-webservice - path: {file_path}, size: {file_size} bytes",
            )

            with open(file_path, "rb") as audio_file:
                file_name = os.path.basename(file_path)
                files = {"audio_file": (file_name, audio_file, "audio/mpeg")}
                # Request JSON output with word-level timestamps.
                params = {
                    "output": "json",
                    "encode": "true",
                    "word_timestamps": "true",
                }

                logger.info(
                    f"Entry {entry_id or 'unknown'}: Sending to whisper-asr-webservice at {self.whisper_asr_url}/asr",
                )

                response = httpx.post(
                    f"{self.whisper_asr_url}/asr",
                    files=files,
                    params=params,
                    timeout=600.0,  # Long timeout for large files
                )
                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError:
                    # Older whisper-asr-webservice builds may not honor output=json;
                    # fall back to raw text without timing data.
                    transcript = response.text.strip()
                    logger.warning(
                        f"Entry {entry_id or 'unknown'}: whisper-asr-webservice returned non-JSON output, "
                        "word- and segment-level timestamps unavailable",
                    )
                    return (transcript or None), None, None

                text = (payload.get("text") or "").strip() or None
                normalized_words: list[dict[str, Any]] = []
                normalized_segments: list[dict[str, Any]] = []
                for segment in payload.get("segments") or []:
                    seg_norm = self._normalize_segment_entry(segment)
                    if seg_norm is not None:
                        normalized_segments.append(seg_norm)
                    for raw_word in segment.get("words") or []:
                        word_norm = self._normalize_word_entry(raw_word)
                        if word_norm is not None:
                            normalized_words.append(word_norm)

                logger.info(
                    f"Entry {entry_id or 'unknown'}: whisper-asr-webservice transcription completed "
                    f"({len(text) if text else 0} characters, {len(normalized_words)} words, "
                    f"{len(normalized_segments)} segments)",
                )
                return text, (normalized_words or None), (normalized_segments or None)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"whisper-asr-webservice HTTP error: {e.response.status_code} - {e.response.text}",
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"whisper-asr-webservice request error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"whisper-asr-webservice error: {str(e)}")
            raise

    def validate_audio_file(self, s3_key: str) -> tuple[bool, str | None]:
        """Validate audio file in S3 for transcription - allows large files for chunking"""

        try:
            logger.info(f"ASR validation starting for S3 key: {s3_key}")

            # Get file info for debugging
            file_info = self.s3_service.get_file_info(s3_key)
            if file_info:
                file_size = file_info.get("size", 0)
                logger.info(
                    f"ASR validation - file size: {file_size} bytes ({file_size / (1024 * 1024):.1f} MB)",
                )
                logger.info(
                    f"ASR validation - max_upload_size: {settings.max_upload_size} bytes ({settings.max_upload_size / (1024 * 1024):.1f} MB)",
                )
                logger.info(
                    f"ASR validation - max_file_size (Groq chunk): {settings.max_file_size} bytes ({settings.max_file_size / (1024 * 1024):.1f} MB)",
                )

            # Use audio conversion service for format validation only
            # This will check if the file can be converted to MP3/Groq format
            logger.info(
                "ASR validation - calling audio_conversion_service.validate_input_file",
            )
            validation_success, validation_error = (
                self.audio_conversion_service.validate_input_file(s3_key)
            )

            if not validation_success:
                # Check if this is a size-related error that we should ignore
                size_related_keywords = [
                    "too large",
                    "file size",
                    "groq processing",
                    "max:",
                    "bytes",
                    "exceeds",
                    "26214400",
                    "34046591",
                    "47700599",
                    "file too large for groq",
                    "file too large for groq processing",
                    "(max:",
                    "file too large for upload",
                    "file too large for conversion",
                    "size exceeds",
                    "file size exceeds",
                ]
                is_size_error = validation_error and any(
                    keyword in validation_error.lower()
                    for keyword in size_related_keywords
                )

                if is_size_error:
                    logger.warning(
                        f"ASR validation - ignoring size-related error (chunking will handle): {validation_error}",
                    )
                    # Allow the file to proceed - chunking will handle size issues
                    return True, None
                else:
                    logger.error(
                        f"ASR validation - audio conversion validation failed: {validation_error}",
                    )
                    return False, validation_error

            # Note: We do NOT validate file size against Groq limits here
            # Large files will be automatically chunked during transcription
            # Only the audio conversion service validates against max_upload_size

            logger.info(
                "ASR validation - SUCCESS - file will be processed with chunking if needed",
            )
            return True, None

        except Exception as e:
            error_msg = f"File validation error: {str(e)}"
            logger.error(f"ASR validation - exception: {error_msg}")
            return False, error_msg

    def get_supported_formats(self) -> list[str]:
        """Get list of supported input formats (can be converted to MP3 for Groq)"""
        return self.audio_conversion_service.get_supported_input_formats()

    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if an ASR error is permanent and should not be retried"""

        # Check if it's a conversion service permanent error
        if self.audio_conversion_service.is_permanent_error(error_message):
            return True

        permanent_error_patterns = [
            "File not found",
            "Unsupported file format",
            "File too large for upload",  # Only permanent if it exceeds upload limit
            "File too large for conversion",  # Only permanent if it exceeds conversion limit
            "File is empty",
            "File validation failed",
            "Invalid API key",
            "Unauthorized",
            "authentication",
            "invalid_request_error",
            "invalid file format",
            "unsupported media type",
            "Failed to convert file to Groq-compatible format",
        ]

        return any(
            pattern.lower() in error_message.lower()
            for pattern in permanent_error_patterns
        )

    async def health_check(self) -> bool:
        """Check if ASR provider, audio conversion, and chunking services are accessible"""

        try:
            # Check provider-specific health
            if self.provider == ASRProvider.GROQ:
                provider_healthy = (
                    self.client is not None and settings.groq_api_key is not None
                )
                if not provider_healthy:
                    logger.error("Groq API client is not properly initialized")
            elif self.provider == ASRProvider.WHISPER_ASR:
                # Check if whisper-asr-webservice is reachable
                try:
                    response = httpx.get(f"{self.whisper_asr_url}/", timeout=10.0)
                    provider_healthy = response.status_code == 200
                    if not provider_healthy:
                        logger.error(
                            f"whisper-asr-webservice returned status {response.status_code}",
                        )
                except Exception as e:
                    logger.error(f"whisper-asr-webservice not reachable: {str(e)}")
                    provider_healthy = False
            else:
                provider_healthy = False
                logger.error(f"Unknown ASR provider: {self.provider}")

            # Check if audio conversion service is healthy (FFmpeg available)
            conversion_healthy = await self.audio_conversion_service.health_check()

            # Check if chunking service is healthy (FFmpeg available) - only needed for Groq
            if self.provider == ASRProvider.GROQ:
                chunking_healthy = await self.audio_chunking_service.health_check()
            else:
                chunking_healthy = True  # Not needed for whisper-asr-webservice

            if not conversion_healthy:
                logger.error("Audio conversion service is not healthy")

            if not chunking_healthy:
                logger.error("Audio chunking service is not healthy")

            return provider_healthy and conversion_healthy and chunking_healthy

        except Exception as e:
            logger.error(f"ASR service health check failed: {str(e)}")
            return False
