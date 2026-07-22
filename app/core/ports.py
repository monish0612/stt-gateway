"""Hexagonal ports — providers plug in behind these ABCs."""

from abc import ABC, abstractmethod

from .models import TranscriptResult


class TranscriptionPort(ABC):
    @abstractmethod
    async def transcribe(
        self, audio: bytes, filename: str, language: str | None
    ) -> TranscriptResult: ...


class CorrectionPort(ABC):
    @abstractmethod
    async def correct(
        self, raw_text: str, vocabulary: list[str], language: str | None
    ) -> str: ...
