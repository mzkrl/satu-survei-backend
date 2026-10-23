from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from apps.agents.llm import (
    AnthropicClient,
    FakeLLMClient,
    LLMClient,
    LLMProviderError,
    LLMResponse,
    get_llm_client,
)


class _MessagesOk:
    def __init__(self) -> None:
        self.kwargs: dict = {}
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="halo dunia")],
            model="stub-model",
        )


class _MessagesTimeout:
    def __init__(self) -> None:
        self.messages = self

    def create(self, **kwargs):
        raise anthropic.APITimeoutError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        )


def test_fake_client_returns_queued_responses_in_order() -> None:
    client = FakeLLMClient(["{}", '{"a": 1}'])
    first = client.complete(system="s1", user="u1", timeout_s=10)
    second = client.complete(system="s2", user="u2", timeout_s=20)
    assert isinstance(first, LLMResponse)
    assert first.text == "{}"
    assert second.text == '{"a": 1}'
    assert [c.system for c in client.calls] == ["s1", "s2"]
    assert [c.user for c in client.calls] == ["u1", "u2"]
    assert [c.timeout_s for c in client.calls] == [10, 20]


def test_fake_client_can_raise_queued_exception() -> None:
    client = FakeLLMClient([LLMProviderError("gagal sekali"), "ok"])
    with pytest.raises(LLMProviderError):
        client.complete(system="s", user="u", timeout_s=10)
    assert client.complete(system="s", user="u", timeout_s=10).text == "ok"


def test_fake_client_empty_queue_raises() -> None:
    client = FakeLLMClient()
    with pytest.raises(LLMProviderError):
        client.complete(system="s", user="u", timeout_s=10)


def test_fake_client_queue_extends_responses() -> None:
    client = FakeLLMClient()
    client.queue("a", "b")
    assert client.complete(system="s", user="u", timeout_s=1).text == "a"
    assert client.complete(system="s", user="u", timeout_s=1).text == "b"


def test_fake_client_satisfies_protocol() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)


def test_get_llm_client_defaults_to_fake(settings) -> None:
    settings.LLM_PROVIDER = "fake"
    assert isinstance(get_llm_client(), FakeLLMClient)


def test_get_llm_client_anthropic_without_key_raises(settings) -> None:
    settings.LLM_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    settings.LLM_MODEL = "claude-test"
    with pytest.raises(LLMProviderError):
        get_llm_client()


def test_get_llm_client_anthropic_without_model_raises(settings) -> None:
    settings.LLM_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.LLM_MODEL = ""
    with pytest.raises(LLMProviderError):
        get_llm_client()


def test_get_llm_client_anthropic_builds_client_without_network(settings) -> None:
    settings.LLM_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.LLM_MODEL = "claude-test"
    client = get_llm_client()
    assert isinstance(client, AnthropicClient)


def test_get_llm_client_passes_base_url(settings) -> None:
    settings.LLM_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.LLM_MODEL = "claude-test"
    settings.ANTHROPIC_BASE_URL = "https://router.example.com/v1"
    client = get_llm_client()
    assert isinstance(client, AnthropicClient)
    assert str(client._client.base_url).rstrip("/") == "https://router.example.com/v1"


def test_anthropic_client_returns_text_response() -> None:
    stub = _MessagesOk()
    client = AnthropicClient(api_key="sk-test", model="claude-test", client=stub)
    response = client.complete(system="sistem", user="pengguna", timeout_s=30)
    assert response.text == "halo dunia"
    assert response.model == "stub-model"
    assert response.latency_ms >= 0
    assert stub.kwargs["model"] == "claude-test"
    assert stub.kwargs["system"] == "sistem"
    assert stub.kwargs["timeout"] == 30
    assert stub.kwargs["messages"] == [{"role": "user", "content": "pengguna"}]


def test_anthropic_client_maps_timeout_to_provider_error() -> None:
    client = AnthropicClient(api_key="sk-test", model="claude-test", client=_MessagesTimeout())
    with pytest.raises(LLMProviderError) as excinfo:
        client.complete(system="s", user="u", timeout_s=5)
    assert "APITimeoutError" in str(excinfo.value)
