"""GET /healthz — liveness + a cheap Groq reachability probe."""

import httpx
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    groq_status = "unknown"
    client: httpx.AsyncClient | None = getattr(
        request.app.state, "http_client", None
    )
    if client is not None:
        try:
            # HEAD to the API root — we only care that the host resolves and
            # answers; any HTTP status counts as reachable.
            await client.head("https://api.groq.com", timeout=3.0)
            groq_status = "reachable"
        except httpx.HTTPError:
            groq_status = "unreachable"
    return {"status": "ok", "groq": groq_status}
