"""Orchestration rules: correction gating + graceful degradation."""

import pytest

from app.core.models import TranscribeOptions, TranscriptResult
from app.core.ports import CorrectionPort, TranscriptionPort
from app.core.service import TranscribeService


class FakeTranscriber(TranscriptionPort):
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def transcribe(self, audio, filename, language):
        self.calls += 1
        return TranscriptResult(raw_text=self.text, provider="fake", stt_latency_ms=5)


class FakeCorrector(CorrectionPort):
    def __init__(self, corrected: str = "corrected text goes here") -> None:
        self.corrected = corrected
        self.calls = 0

    async def correct(self, raw_text, vocabulary, language):
        self.calls += 1
        return self.corrected


class ExplodingCorrector(CorrectionPort):
    async def correct(self, raw_text, vocabulary, language):
        raise RuntimeError("gemini down")


@pytest.mark.asyncio
async def test_correction_applied_for_long_utterance():
    corrector = FakeCorrector("Add fifty rupees for coffee.")
    service = TranscribeService(
        FakeTranscriber("add fifty rupees for coffee"), corrector
    )
    result = await service.run(b"x", "a.m4a", TranscribeOptions())
    assert result.corrected_text == "Add fifty rupees for coffee."
    assert result.final_text == "Add fifty rupees for coffee."
    assert corrector.calls == 1


@pytest.mark.asyncio
async def test_correction_skipped_for_short_utterance():
    corrector = FakeCorrector()
    service = TranscribeService(FakeTranscriber("hello there"), corrector)
    result = await service.run(b"x", "a.m4a", TranscribeOptions())
    assert result.corrected_text is None
    assert result.final_text == "hello there"
    assert corrector.calls == 0


@pytest.mark.asyncio
async def test_correction_skipped_when_disabled_per_request():
    corrector = FakeCorrector()
    service = TranscribeService(
        FakeTranscriber("one two three four five"), corrector
    )
    result = await service.run(
        b"x", "a.m4a", TranscribeOptions(correct=False)
    )
    assert result.corrected_text is None
    assert corrector.calls == 0


@pytest.mark.asyncio
async def test_correction_failure_degrades_to_raw_text():
    service = TranscribeService(
        FakeTranscriber("this is the raw transcript text"), ExplodingCorrector()
    )
    result = await service.run(b"x", "a.m4a", TranscribeOptions())
    assert result.corrected_text is None
    assert result.final_text == "this is the raw transcript text"


@pytest.mark.asyncio
async def test_correction_globally_disabled():
    corrector = FakeCorrector()
    service = TranscribeService(
        FakeTranscriber("one two three four five"),
        corrector,
        correction_enabled=False,
    )
    result = await service.run(b"x", "a.m4a", TranscribeOptions())
    assert result.corrected_text is None
    assert corrector.calls == 0
