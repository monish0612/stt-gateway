"""GroqWhisperAdapter — primary transcription provider.

Calls Groq's OpenAI-compatible audio transcription endpoint with
``whisper-large-v3-turbo`` (~1s for a 30s clip). Uses a single shared
``httpx.AsyncClient`` (created in the FastAPI lifespan) with HTTP/2 and
keep-alive so repeat requests skip the ~200ms TLS handshake.
"""

import logging
import time

import httpx

from ..core.models import TranscriptResult
from ..core.ports import TranscriptionPort

logger = logging.getLogger("stt-gateway.groq")

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class TranscriptionError(Exception):
    """Raised when the provider could not produce a transcript."""


class GroqWhisperAdapter(TranscriptionPort):
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self, audio: bytes, filename: str, language: str | None
    ) -> TranscriptResult:
        data: dict[str, str] = {
            "model": self._model,
            "response_format": "json",
            "temperature": "0",
        }
        if language:
            data["language"] = language

        started = time.perf_counter()
        try:
            response = await self._client.post(
                GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=data,
                files={"file": (filename, audio)},
            )
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Groq request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            body = response.text[:500]
            logger.error("Groq returned %s: %s", response.status_code, body)
            raise TranscriptionError(
                f"Groq returned {response.status_code}"
            )

        try:
            text = response.json().get("text", "")
        except ValueError as exc:
            raise TranscriptionError("Groq returned non-JSON body") from exc

        logger.info("Groq transcribed %d bytes in %dms", len(audio), latency_ms)
        return TranscriptResult(
            raw_text=text.strip(),
            provider="groq",
            stt_latency_ms=latency_ms,
        )
