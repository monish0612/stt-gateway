"""Request dependencies: client-key auth + per-client daily rate cap."""

import logging
from collections import defaultdict
from datetime import date

from fastapi import Header, HTTPException, Request

from ..config import Settings, get_settings

logger = logging.getLogger("stt-gateway.auth")

# In-memory per-client daily counter — deliberately simple. A leaked key
# can't run up provider usage past the daily cap; restarting the container
# resets it, which is fine at this scale.
_request_counts: dict[str, int] = defaultdict(int)
_count_day: date = date.today()


def _bump_and_check(client: str, limit: int) -> bool:
    global _count_day
    today = date.today()
    if today != _count_day:
        _request_counts.clear()
        _count_day = today
    _request_counts[client] += 1
    return _request_counts[client] <= limit


async def require_client(
    request: Request,
    x_client_key: str | None = Header(default=None),
) -> str:
    """Resolve the X-Client-Key header to a client name or raise 401/429."""
    settings: Settings = get_settings()
    key_map = settings.client_key_map

    if not x_client_key or x_client_key not in key_map:
        raise HTTPException(status_code=401, detail="Invalid or missing client key")

    client = key_map[x_client_key]
    if not _bump_and_check(client, settings.daily_request_limit):
        logger.warning("Client %s exceeded daily request limit", client)
        raise HTTPException(status_code=429, detail="Daily request limit exceeded")

    return client
