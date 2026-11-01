from __future__ import annotations

from typing import Any

import pytest

from apps.agents.llm import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    LLMClient,
    LLMProviderError,
    LLMResponse,
    QwenClient,
    get_llm_client,
)


class _StubTransport:
    """Transport HTTP palsu untuk QwenClient tanpa koneksi jaringan."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        self.calls.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        if not self._responses:
            raise RuntimeError("tidak ada sisa respons")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return item
        return {
            "choices": [{"message": {"content": item}}],
            "model": json["model"],
        }


def _make_client(
    responses: list[Any] | None = None,
    *,
    model: str = "qwen-flash",
    base_url: str = DEFAULT_QWEN_BASE_URL,
    api_key: str = "sk-ws-test",
) -> tuple[QwenClient, _StubTransport]:
    transport = _StubTransport(responses)
    client = QwenClient(
        api_key=api_key,
        model=model,
        base_url=base_url,
        transport=transport,
    )
    return client, transport


# -- Tes QwenClient -----------------------------------------------------------


def test_qwen_client_returns_llm_response() -> None:
    client, _ = _make_client(["jawaban qwen"])
    response = client.complete(system="sistem", user="pengguna", timeout_s=30)

    assert isinstance(response, LLMResponse)
    assert response.text == "jawaban qwen"
    assert response.model == "qwen-flash"
    assert response.latency_ms >= 0


def test_qwen_client_sends_qwen_flash_request() -> None:
    client, transport = _make_client(["ok"], base_url=DEFAULT_QWEN_BASE_URL + "/")
    client.complete(system="S", user="U", timeout_s=15)

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == f"{DEFAULT_QWEN_BASE_URL}/chat/completions"
    assert call["timeout"] == 15
    assert call["headers"]["Authorization"] == "Bearer sk-ws-test"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["json"]["model"] == "qwen-flash"
    assert call["json"]["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]


def test_qwen_client_accepts_custom_model() -> None:
    client, transport = _make_client(["ok"], model="qwen-flash")
    response = client.complete(system="S", user="U", timeout_s=5)

    assert response.model == "qwen-flash"
    assert transport.calls[0]["json"]["model"] == "qwen-flash"


def test_qwen_client_wraps_transport_error() -> None:
    client, _ = _make_client([RuntimeError("jaringan putus")])
    with pytest.raises(LLMProviderError) as exc_info:
        client.complete(system="s", user="u", timeout_s=10)

    assert "Qwen Cloud" in str(exc_info.value)
    assert "jaringan putus" in str(exc_info.value)


def test_qwen_client_rejects_invalid_response() -> None:
    client, _ = _make_client([{"choices": []}])
    with pytest.raises(LLMProviderError, match="respons tidak valid"):
        client.complete(system="s", user="u", timeout_s=10)


def test_qwen_client_falls_back_to_configured_model() -> None:
    client, _ = _make_client(
        [{"choices": [{"message": {"content": "teks"}}]}],
        model="model-cadangan",
    )
    assert client.complete(system="s", user="u", timeout_s=1).model == "model-cadangan"


def test_qwen_client_satisfies_llm_client_protocol() -> None:
    client, _ = _make_client()
    assert isinstance(client, LLMClient)


# -- Tes get_llm_client -------------------------------------------------------


def test_get_llm_client_uses_qwen_cloud(settings) -> None:
    settings.QWEN_API_KEY = "sk-ws-test"
    settings.QWEN_MODEL = "qwen-flash"
    settings.QWEN_BASE_URL = "https://contoh.qwencloudapi.com/compatible-mode/v1"
    settings.LLM_MODEL = ""

    client = get_llm_client()

    assert isinstance(client, QwenClient)
    assert client._model == "qwen-flash"
    assert client._base_url == "https://contoh.qwencloudapi.com/compatible-mode/v1"


def test_get_llm_client_default_model_and_base_url(settings) -> None:
    settings.QWEN_API_KEY = "sk-ws-test"
    settings.QWEN_MODEL = ""
    settings.QWEN_BASE_URL = ""
    settings.LLM_MODEL = ""

    client = get_llm_client()

    assert client._model == DEFAULT_QWEN_MODEL
    assert client._base_url == DEFAULT_QWEN_BASE_URL


def test_get_llm_client_falls_back_to_generic_model(settings) -> None:
    settings.QWEN_API_KEY = "sk-ws-test"
    settings.QWEN_MODEL = ""
    settings.QWEN_BASE_URL = ""
    settings.LLM_MODEL = "model-generik"

    client = get_llm_client()

    assert client._model == "model-generik"


def test_get_llm_client_without_key_raises(settings) -> None:
    settings.QWEN_API_KEY = ""

    with pytest.raises(LLMProviderError, match="QWEN_API_KEY"):
        get_llm_client()
