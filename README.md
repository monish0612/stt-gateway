# stt-gateway

Ultra-fast, near-zero-cost speech-to-text gateway for the AI Nexus Android app
(and the website later). Thin FastAPI service: audio in → Groq Whisper Large v3
Turbo (~1s) → optional Gemini Flash-Lite correction pass (~0.5s) → JSON out.
API keys stay server-side; audio is streamed through memory and never touches disk.

## Architecture

```
Flutter app ──POST /v1/transcribe (m4a)──▶ stt-gateway ──▶ Groq whisper-large-v3-turbo
     ▲                                        │
     └────────── {text, raw_text, ...} ◀──────┴──▶ Gemini Flash-Lite (cleanup, optional)
```

Hexagonal layout: `core/ports.py` defines `TranscriptionPort` / `CorrectionPort`;
providers are swappable adapters under `app/adapters/`.

Orchestration rules (`core/service.py`):
- Correction runs only when requested AND the transcript has ≥ 4 words.
- Correction failure is never fatal — the raw transcript is returned.
- Both `raw_text` and corrected `text` are returned for diffing/debugging.

## API

### `POST /v1/transcribe`

- Auth header: `X-Client-Key: <key>` (keys configured via `CLIENT_KEYS=android:abc,web:def`)
- Body `multipart/form-data`:
  - `file` — audio (m4a, wav, mp3, webm, ogg, …)
  - `language` (optional) — ISO code, omit for auto-detect
  - `correct` (optional, default `true`)
  - `vocabulary` (optional) — comma-separated domain terms
- `200` response:

```json
{
  "text": "Corrected final text to insert.",
  "raw_text": "corrected final text too insert",
  "provider": "groq",
  "stt_latency_ms": 940,
  "correction_latency_ms": 480
}
```

- Errors: `401` bad key · `413` too large · `422` bad format · `429` daily cap ·
  `502` provider failed (client falls back to on-device STT)

### `GET /healthz` → `{"status":"ok","groq":"reachable"}`

## Local development

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                              # fill in GROQ_API_KEY etc.
uvicorn app.main:app --reload --port 8080
pytest
```

Smoke test:

```bash
curl -F "file=@test.m4a" -H "X-Client-Key: YOUR_ANDROID_KEY" \
  http://localhost:8080/v1/transcribe
```

## Deployment (Coolify)

1. Push this folder as its own repo (or point Coolify at the subfolder).
2. Coolify → New Resource → Dockerfile/Compose build from this repo.
3. Set env vars from `.env.example` — `GROQ_API_KEY` and `GEMINI_API_KEY`
   can reuse the same values already configured for the ainexus stack;
   generate a long random value for the `android:` entry in `CLIENT_KEYS`.
4. Map port `8080` (the app expects `http://<vps-ip>:8080` by default,
   overridable in Flutter with `--dart-define=STT_GATEWAY_URL=...`).
5. Memory limit 512 MB is plenty (bump only if local whisper is enabled later).

## Flutter client

The app records a parallel 16 kHz mono AAC (m4a) clip while on-device STT runs,
shows the on-device transcript instantly, then uploads the clip here and silently
swaps in the corrected text if the user hasn't edited the field. Any gateway
failure leaves the on-device transcript untouched — the feature degrades, never
breaks. See `ai_nexus/lib/data/services/stt_gateway_service.dart`.
