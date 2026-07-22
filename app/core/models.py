"""Core dataclasses shared by ports, adapters and the orchestrator."""

from dataclasses import dataclass, field


@dataclass
class TranscriptResult:
    raw_text: str
    corrected_text: str | None = None
    provider: str = "groq"
    stt_latency_ms: int = 0
    correction_latency_ms: int = 0

    @property
    def final_text(self) -> str:
        """Corrected text when available, otherwise the raw transcript."""
        return self.corrected_text or self.raw_text


@dataclass
class TranscribeOptions:
    language: str | None = None          # e.g. "en", "ta"; None = auto-detect
    correct: bool = True                 # skip correction pass if False (faster)
    vocabulary: list[str] = field(default_factory=list)  # app-specific terms
