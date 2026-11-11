from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_FENCE_START = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_END = re.compile(r"\s*```$")


def configured_models() -> list[str]:
    """Primary model followed by configured fallbacks, without duplicates."""
    raw_models = [settings.QWEN_MODEL, *(settings.LLM_FALLBACK_MODELS or "").split(",")]
    models: list[str] = []
    for raw in raw_models:
        model = (raw or "").strip()
        if model and model not in models:
            models.append(model)
    return models


def _first_json_object(text: str) -> str | None:
    """Return the first balanced {...} block, ignoring braces inside strings."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from plain, fenced, or prose-wrapped model output."""
    raw = (text or "").strip()
    if not raw:
        return None
    raw = _FENCE_END.sub("", _FENCE_START.sub("", raw)).strip()

    candidates = [raw]
    block = _first_json_object(raw)
    if block and block != raw:
        candidates.append(block)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _make_client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.QWEN_API_KEY,
        base_url=settings.QWEN_BASE_URL,
        timeout=float(settings.LLM_TIMEOUT_SECONDS),
        max_retries=int(settings.LLM_MAX_RETRIES),
    )


def chat_json(prompt: str) -> tuple[dict[str, Any], str] | None:
    """Call the primary model, then fallbacks, until one returns valid JSON.

    Returns ``(parsed_json, model_used)`` or ``None`` when every model fails.
    ``stream=False`` is always sent explicitly: some 9router providers return
    SSE when the field is omitted even for non-streaming requests.
    """
    if not getattr(settings, "QWEN_API_KEY", ""):
        return None

    models = configured_models()
    if not models:
        return None

    try:
        client = _make_client()
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        logger.warning("LLM client is unavailable: %s", exc)
        return None

    for index, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            data = extract_json_object(content)
            if data is None:
                raise ValueError("response did not contain a valid JSON object")
            used = getattr(response, "model", None) or model
            if index:
                logger.warning(
                    "LLM fallback used: %s (primary %s unavailable/failed)",
                    used,
                    models[0],
                )
            return data, used
        except Exception as exc:
            logger.warning("LLM call failed for model %s: %s", model, exc)

    logger.error("All configured LLM models failed: %s", ", ".join(models))
    return None