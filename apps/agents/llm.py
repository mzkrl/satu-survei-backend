from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import anthropic
from django.conf import settings


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


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: object | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        if client is not None:
            self._client = client
        else:
            kwargs: dict[str, str] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.Anthropic(**kwargs)

    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = self._client.messages.create(  # type: ignore[attr-defined]
                model=self._model,
                system=system,
                max_tokens=4096,
                timeout=timeout_s,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Provider LLM gagal: {exc.__class__.__name__}") from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(text=text, model=str(response.model or self._model), latency_ms=latency_ms)


@dataclass
class FakeCall:
    system: str
    user: str
    timeout_s: int


class FakeLLMClient:
    def __init__(self, responses: list[str | Exception] | None = None, *, model: str = "fake-model") -> None:
        self._responses: list[str | Exception] = list(responses or [])
        self._model = model
        self.calls: list[FakeCall] = []

    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse:
        self.calls.append(FakeCall(system=system, user=user, timeout_s=timeout_s))
        if not self._responses:
            raise LLMProviderError("FakeLLMClient: tidak ada sisa respons.")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model=self._model, latency_ms=1)

    def queue(self, *responses: str | Exception) -> None:
        self._responses.extend(responses)


def get_llm_client() -> LLMClient:
    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        api_key = settings.ANTHROPIC_API_KEY
        model = settings.LLM_MODEL
        if not api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY belum diatur.")
        if not model:
            raise LLMProviderError("LLM_MODEL belum diatur.")
        base_url = settings.ANTHROPIC_BASE_URL or None
        return AnthropicClient(api_key=api_key, model=model, base_url=base_url)
    return FakeLLMClient()
