"""Environment-driven settings for the stt-gateway service.

Everything is configured via env vars (Coolify UI / docker-compose `.env`).
No secrets ever ship to clients — the app only holds a per-client key that
maps to an entry in ``CLIENT_KEYS``.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Provider credentials (server-side only) ─────────────────────────
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # ── Client auth ─────────────────────────────────────────────────────
    # Format: "android:abc123,web:def456". The client sends the value part
    # in the X-Client-Key header; we resolve it back to the client name.
    client_keys: str = ""

    # ── Behaviour toggles ───────────────────────────────────────────────
    correction_enabled: bool = True
    local_whisper_enabled: bool = False  # reserved for the future fallback

    # ── Limits / networking ─────────────────────────────────────────────
    max_upload_mb: int = 15
    cors_origins: str = ""  # comma-separated origins for the future web app
    log_level: str = "INFO"

    # Per-client daily request cap (leaked-key damage control).
    daily_request_limit: int = 2000

    # ── Provider tunables ───────────────────────────────────────────────
    groq_model: str = "whisper-large-v3-turbo"
    gemini_model: str = "gemini-2.5-flash-lite"

    @model_validator(mode="after")
    def _require_provider_keys(self) -> "Settings":
        missing = [
            name
            for name, value in (
                ("GROQ_API_KEY", self.groq_api_key),
                ("GEMINI_API_KEY", self.gemini_api_key),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(
                "stt-gateway refuses to start; missing "
                + ", ".join(missing)
                + ". Set the Coolify team variable and redeploy."
            )
        return self

    @property
    def client_key_map(self) -> dict[str, str]:
        """Map of raw key value → client name (e.g. {"abc123": "android"})."""
        result: dict[str, str] = {}
        for pair in self.client_keys.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            name, key = pair.split(":", 1)
            if key:
                result[key] = name
        return result

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
