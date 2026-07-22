"""GeminiCorrectionAdapter — post-STT cleanup pass.

Uses Gemini Flash-Lite (temperature 0) to fix homophones, punctuation,
casing and mis-heard words WITHOUT paraphrasing. Latency-sensitive: hard
4s timeout, and any failure is surfaced as an exception which the
orchestrator converts into a graceful raw-text fallback.
"""

import asyncio
import logging

from google import genai
from google.genai import types

from ..core.ports import CorrectionPort

logger = logging.getLogger("stt-gateway.gemini")

CORRECTION_TIMEOUT_S = 4.0

SYSTEM_PROMPT = (
    "You fix speech-to-text transcription errors. Correct homophones, "
    "punctuation, casing, and obvious mis-heard words. Preserve the "
    "speaker's meaning, language, and phrasing. Do NOT paraphrase, "
    "summarize, or add anything.\n"
    "Known domain terms (prefer these spellings): {vocabulary}\n"
    "Return ONLY the corrected text. No preamble, no quotes, no markdown."
)


class GeminiCorrectionAdapter(CorrectionPort):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def correct(
        self, raw_text: str, vocabulary: list[str], language: str | None
    ) -> str:
        vocab = ", ".join(vocabulary) if vocabulary else "(none)"
        system = SYSTEM_PROMPT.format(vocabulary=vocab)

        # Cheap guardrail: the corrected text should be roughly the same
        # length as the input — cap output at ~1.5x the input token estimate.
        max_tokens = max(64, int(len(raw_text.split()) * 2))

        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model,
                contents=raw_text,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    max_output_tokens=max_tokens,
                ),
            ),
            timeout=CORRECTION_TIMEOUT_S,
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Gemini returned empty correction")
        return text
