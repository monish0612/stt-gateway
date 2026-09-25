"""API-level tests: auth, validation, provider-failure mapping."""

import os

os.environ.setdefault("GROQ_API_KEY", "unused")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("CLIENT_KEYS", "android:testkey123")

import pytest
from fastapi.testclient import TestClient

from app.adapters.groq_whisper import TranscriptionError
from app.config import get_settings
from app.core.models import TranscriptResult
from app.core.ports import CorrectionPort, TranscriptionPort
from app.core.service import TranscribeService
from app.main import create_app


class FakeTranscriber(TranscriptionPort):
    def __init__(self, text="hello world this is a test", fail=False):
        self.text = text
        self.fail = fail

    async def transcribe(self, audio, filename, language):
        if self.fail:
            raise TranscriptionError("provider down")
        return TranscriptResult(raw_text=self.text, provider="fake", stt_latency_ms=7)


class FakeCorrector(CorrectionPort):
    async def correct(self, raw_text, vocabulary, language):
        return raw_text.capitalize() + "."


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CLIENT_KEYS", "android:testkey123")
    monkeypatch.setenv("GROQ_API_KEY", "unused")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as test_client:
        # Swap the real adapters for fakes after lifespan wiring.
        app.state.transcribe_service = TranscribeService(
            FakeTranscriber(), FakeCorrector()
        )
        yield test_client

    get_settings.cache_clear()


def _post(client, key="testkey123", filename="clip.m4a", data=None):
    headers = {"X-Client-Key": key} if key else {}
    return client.post(
        "/v1/transcribe",
        headers=headers,
        files={"file": (filename, b"fake-audio-bytes", "audio/mp4")},
        data=data or {},
    )


def test_missing_client_key_rejected(client):
    response = _post(client, key=None)
    assert response.status_code == 401


def test_wrong_client_key_rejected(client):
    response = _post(client, key="not-a-key")
    assert response.status_code == 401


def test_happy_path_returns_corrected_and_raw(client):
    response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["raw_text"] == "hello world this is a test"
    assert body["text"] == "Hello world this is a test."
    assert body["provider"] == "fake"


def test_unsupported_extension_rejected(client):
    response = _post(client, filename="clip.txt")
    assert response.status_code == 422


def test_oversized_file_rejected(client):
    response = client.post(
        "/v1/transcribe",
        headers={"X-Client-Key": "testkey123"},
        files={"file": ("big.m4a", b"x" * (1024 * 1024 + 1), "audio/mp4")},
    )
    assert response.status_code == 413


def test_provider_failure_maps_to_502(client):
    client.app.state.transcribe_service = TranscribeService(
        FakeTranscriber(fail=True), FakeCorrector()
    )
    response = _post(client)
    assert response.status_code == 502


def test_correct_false_skips_correction(client):
    response = _post(client, data={"correct": "false"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == body["raw_text"]


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
