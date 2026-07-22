"""FastAPI app factory for stt-gateway.

Wiring happens here: one shared httpx client (HTTP/2 + keep-alive) lives
for the whole process, adapters are constructed once, and the orchestrating
``TranscribeService`` is stashed on ``app.state`` for the routes.
"""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters.gemini_corrector import GeminiCorrectionAdapter
from .adapters.groq_whisper import GroqWhisperAdapter
from .adapters.noop_corrector import NoopCorrectionAdapter
from .api.routes_health import router as health_router
from .api.routes_transcribe import router as transcribe_router
from .config import get_settings
from .core.ports import CorrectionPort
from .core.service import TranscribeService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    # Shared client: HTTP/2 + keep-alive saves ~200ms TLS handshake per call.
    http_client = httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(15.0, connect=3.0),
        limits=httpx.Limits(max_keepalive_connections=10),
    )
    app.state.http_client = http_client

    transcriber = GroqWhisperAdapter(
        client=http_client,
        api_key=settings.groq_api_key,
        model=settings.groq_model,
    )

    corrector: CorrectionPort
    if settings.correction_enabled and settings.gemini_api_key:
        corrector = GeminiCorrectionAdapter(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
    else:
        corrector = NoopCorrectionAdapter()

    app.state.transcribe_service = TranscribeService(
        transcriber=transcriber,
        corrector=corrector,
        correction_enabled=settings.correction_enabled,
    )

    yield

    await http_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="stt-gateway", version="1.0.0", lifespan=lifespan)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["POST", "GET"],
            allow_headers=["X-Client-Key", "Content-Type"],
        )

    app.include_router(transcribe_router)
    app.include_router(health_router)
    return app


app = create_app()
