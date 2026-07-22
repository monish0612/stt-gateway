"""Pass-through corrector used when correction is disabled or unconfigured."""

from ..core.ports import CorrectionPort


class NoopCorrectionAdapter(CorrectionPort):
    async def correct(
        self, raw_text: str, vocabulary: list[str], language: str | None
    ) -> str:
        return raw_text
