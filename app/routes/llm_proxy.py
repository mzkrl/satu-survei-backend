"""Authenticated OpenAI-compatible passthrough to the private 9router.

The backend can reach 9router on localhost, while the public internet cannot.
This router lets signed-in clients use the same models through the public API
without ever exposing ``QWEN_API_KEY`` or the private 9router port.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app import models
from app.config import settings
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["LLM Proxy"])

# Only forward endpoints that are part of the OpenAI-compatible surface.
_ALLOWED_PATHS = {
    "models",
    "chat/completions",
    "completions",
    "embeddings",
}

# Headers that must not be copied between the client and 9router.
_SKIP_REQUEST_HEADERS = {
    "authorization",
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "cookie",
}
_SKIP_RESPONSE_HEADERS = {
    "content-length",
    "content-encoding",
    "connection",
    "transfer-encoding",
    "set-cookie",
}


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_llm(
    path: str,
    request: Request,
    _current_user: models.Users = Depends(get_current_user),
):
    """Forward requests to 9router with the server-side API key."""
    if not settings.LLM_PROXY_ENABLED:
        raise HTTPException(status_code=404, detail="LLM proxy disabled")
    if path not in _ALLOWED_PATHS:
        raise HTTPException(status_code=404, detail="Unsupported LLM endpoint")

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _SKIP_REQUEST_HEADERS
    }
    if settings.QWEN_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QWEN_API_KEY}"

    body = await request.body()
    target = f"{settings.QWEN_BASE_URL.rstrip('/')}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=10.0)
    )
    proxy_request = client.build_request(
        request.method,
        target,
        headers=headers,
        content=body or None,
    )
    try:
        upstream = await client.send(proxy_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("llm proxy upstream error: %s", exc)
        raise HTTPException(status_code=502, detail="LLM upstream unavailable") from exc

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _SKIP_RESPONSE_HEADERS
    }

    async def stream_body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )