from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from django.conf import settings

DEFAULT_QWEN_MODEL = "qwen-flash"
DEFAULT_QWEN_BASE_URL = (
    "https://ap-southeast-1.maas.qwencloudapi.com/compatible-mode/v1"
)


class LLMProviderError(Exception):
    """Kegagalan pada provider LLM (jaringan, timeout, konfigurasi)."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    latency_ms: int


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse: ...


class QwenClient:
    """Klien Qwen Cloud lewat endpoint chat completions OpenAI-compatible.

    Implementasi memakai standard library (``urllib``) agar tidak bergantung
    pada SDK provider lain. ``transport`` dapat diinjeksi pada test.
    """

    provider_label = "Qwen Cloud"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_QWEN_BASE_URL,
        transport: object | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or DEFAULT_QWEN_BASE_URL).rstrip("/")
        self._transport = transport

    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse:
        started = time.perf_counter()
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = self._send(payload, timeout_s)
        try:
            text = data["choices"][0]["message"].get("content") or ""
            model = data.get("model") or self._model
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMProviderError(
                f"Provider LLM {self.provider_label} gagal: respons tidak valid ({exc})"
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(text=text, model=model, latency_ms=latency_ms)

    def _send(self, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            if self._transport is not None:
                return self._transport.post(  # type: ignore[attr-defined]
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_s,
                )
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except LLMProviderError:
            raise
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            suffix = f" {detail}" if detail else ""
            raise LLMProviderError(
                f"Provider LLM {self.provider_label} gagal: HTTP {exc.code}{suffix}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                f"Provider LLM {self.provider_label} gagal: {exc}"
            ) from exc


def _clean(value: str | None) -> str:
    return (value or "").strip()


def get_llm_client() -> LLMClient:
    """Membuat klien Qwen Cloud dari konfigurasi ``QWEN_*``.

    ``LLM_MODEL`` tetap didukung sebagai fallback bila ``QWEN_MODEL`` kosong.
    """
    api_key = _clean(getattr(settings, "QWEN_API_KEY", ""))
    if not api_key:
        raise LLMProviderError(
            "QWEN_API_KEY belum dikonfigurasi. Isi QWEN_API_KEY di .env."
        )
    model = (
        _clean(getattr(settings, "QWEN_MODEL", ""))
        or _clean(getattr(settings, "LLM_MODEL", ""))
        or DEFAULT_QWEN_MODEL
    )
    base_url = (
        _clean(getattr(settings, "QWEN_BASE_URL", "")) or DEFAULT_QWEN_BASE_URL
    )
    return QwenClient(api_key=api_key, model=model, base_url=base_url)
