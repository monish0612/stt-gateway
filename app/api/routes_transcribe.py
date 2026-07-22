"""POST /v1/transcribe — the single endpoint clients integrate against."""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..core.models import TranscribeOptions
from ..core.service import TranscribeService
from ..adapters.groq_whisper import TranscriptionError
from ..config import get_settings
from .deps import require_client

logger = logging.getLogger("stt-gateway.transcribe")

router = APIRouter()

# Formats Groq's Whisper endpoint accepts. Checked by extension — cheap and
# good enough; Groq re-validates the actual container server-side.
ALLOWED_EXTENSIONS = {
    "m4a", "mp3", "wav", "webm", "ogg", "flac", "mp4", "mpeg", "mpga", "opus",
}


def get_service(request: Request) -> TranscribeService:
    return request.app.state.transcribe_service


@router.post("/v1/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    correct: bool = Form(default=True),
    vocabulary: str | None = Form(default=None),
    client: str = Depends(require_client),
    service: TranscribeService = Depends(get_service),
) -> dict:
    settings = get_settings()

    filename = file.filename or "audio.m4a"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported format: .{ext}")

    # Stream into memory — no disk writes anywhere in this service.
    audio = await file.read()
    if len(audio) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if not audio:
        raise HTTPException(status_code=422, detail="Empty file")

    options = TranscribeOptions(
        language=language or None,
        correct=correct,
        vocabulary=[v.strip() for v in (vocabulary or "").split(",") if v.strip()],
    )

    try:
        result = await service.run(audio, filename, options)
    except TranscriptionError as exc:
        # 502 tells the client to fall back to on-device STT.
        logger.error("All transcription providers failed for %s: %s", client, exc)
        raise HTTPException(status_code=502, detail="Transcription failed") from exc

    logger.info(
        "client=%s bytes=%d stt=%dms correction=%dms",
        client, len(audio), result.stt_latency_ms, result.correction_latency_ms,
    )
    return {
        "text": result.final_text,
        "raw_text": result.raw_text,
        "provider": result.provider,
        "stt_latency_ms": result.stt_latency_ms,
        "correction_latency_ms": result.correction_latency_ms,
    }
