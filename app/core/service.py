"""TranscribeService — the orchestrator.

Rules (from the architecture spec):
1. Call ``TranscriptionPort.transcribe()`` (Groq primary).
2. If ``options.correct`` and the raw text is >= 4 words, run the correction
   pass. Single-word utterances don't need cleanup — skipping saves latency.
3. Correction is an enhancement, never a blocker: any failure degrades
   gracefully to the raw text.
4. Return both raw and corrected text so clients can diff/debug.
"""

import logging

from .models import TranscribeOptions, TranscriptResult
from .ports import CorrectionPort, TranscriptionPort

logger = logging.getLogger("stt-gateway.service")

# Utterances shorter than this many words skip the correction pass.
MIN_WORDS_FOR_CORRECTION = 4


class TranscribeService:
    def __init__(
        self,
        transcriber: TranscriptionPort,
        corrector: CorrectionPort,
        correction_enabled: bool = True,
    ) -> None:
        self._transcriber = transcriber
        self._corrector = corrector
        self._correction_enabled = correction_enabled

    async def run(
        self, audio: bytes, filename: str, options: TranscribeOptions
    ) -> TranscriptResult:
        result = await self._transcriber.transcribe(
            audio, filename, options.language
        )

        raw = result.raw_text.strip()
        should_correct = (
            self._correction_enabled
            and options.correct
            and len(raw.split()) >= MIN_WORDS_FOR_CORRECTION
        )
        if not should_correct:
            return result

        try:
            corrected = await self._corrector.correct(
                raw, options.vocabulary, options.language
            )
            corrected = (corrected or "").strip()
            if corrected:
                result.corrected_text = corrected
        except Exception:  # noqa: BLE001 — correction must never block
            logger.warning("Correction pass failed — returning raw text", exc_info=True)

        return result
