"""Hermetic tests for app.services.llm_client (no network access)."""

from types import SimpleNamespace

import pytest

from app.services import llm_client
from app.services.llm_client import chat_json, configured_models, extract_json_object


def _response(content, model=None):
    """Build a minimal OpenAI-style chat completion response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
    )


class FakeCompletions:
    """Records calls and delegates response creation to a handler."""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)


def _fake_client(handler):
    completions = FakeCompletions(handler)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    return client, completions


def _patch_settings(monkeypatch, *, api_key, model, fallbacks):
    monkeypatch.setattr(llm_client.settings, "QWEN_API_KEY", api_key)
    monkeypatch.setattr(llm_client.settings, "QWEN_MODEL", model)
    monkeypatch.setattr(llm_client.settings, "LLM_FALLBACK_MODELS", fallbacks)


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------


def test_extract_json_object_plain_object():
    assert extract_json_object('{"claim": "ok", "score": 3}') == {
        "claim": "ok",
        "score": 3,
    }


def test_extract_json_object_fenced_json():
    text = '```json\n{"claim": "fenced", "score": 7}\n```'
    assert extract_json_object(text) == {"claim": "fenced", "score": 7}


def test_extract_json_object_surrounded_by_prose():
    text = 'Here is the extracted result:\n{"claim": "prose", "score": 5}\nHope that helps!'
    assert extract_json_object(text) == {"claim": "prose", "score": 5}


def test_extract_json_object_invalid_text_returns_none():
    assert extract_json_object("this is not json at all") is None


@pytest.mark.parametrize("text", ["", "   ", "\n\t  \n"])
def test_extract_json_object_empty_returns_none(text):
    assert extract_json_object(text) is None


# ---------------------------------------------------------------------------
# configured_models
# ---------------------------------------------------------------------------


def test_configured_models_primary_and_fallbacks_deduped(monkeypatch):
    _patch_settings(
        monkeypatch,
        api_key="test-key",
        model="primary-model",
        fallbacks=" fallback-a , , primary-model, fallback-b,fallback-a ,  ",
    )

    assert configured_models() == ["primary-model", "fallback-a", "fallback-b"]


def test_configured_models_no_fallbacks(monkeypatch):
    _patch_settings(
        monkeypatch,
        api_key="test-key",
        model="primary-model",
        fallbacks="",
    )

    assert configured_models() == ["primary-model"]


# ---------------------------------------------------------------------------
# chat_json
# ---------------------------------------------------------------------------


def test_chat_json_falls_back_after_exception(monkeypatch):
    _patch_settings(
        monkeypatch,
        api_key="test-key",
        model="primary-model",
        fallbacks="fallback-model",
    )

    def handler(kwargs):
        if kwargs["model"] == "primary-model":
            raise RuntimeError("primary unavailable")
        return _response('{"answer": 42}', model="fallback-model")

    client, completions = _fake_client(handler)
    monkeypatch.setattr(llm_client, "_make_client", lambda: client)

    result = chat_json("Extract the claim.")

    assert result == ({"answer": 42}, "fallback-model")
    assert [call["model"] for call in completions.calls] == [
        "primary-model",
        "fallback-model",
    ]
    assert all(call["stream"] is False for call in completions.calls)
    assert all(call["temperature"] == 0 for call in completions.calls)
    assert completions.calls[0]["messages"] == [
        {"role": "user", "content": "Extract the claim."}
    ]


def test_chat_json_returns_none_when_all_models_fail(monkeypatch):
    _patch_settings(
        monkeypatch,
        api_key="test-key",
        model="primary-model",
        fallbacks="fallback-a,fallback-b",
    )

    def handler(kwargs):
        raise RuntimeError(f"{kwargs['model']} is down")

    client, completions = _fake_client(handler)
    monkeypatch.setattr(llm_client, "_make_client", lambda: client)

    assert chat_json("Extract the claim.") is None
    assert [call["model"] for call in completions.calls] == [
        "primary-model",
        "fallback-a",
        "fallback-b",
    ]


@pytest.mark.parametrize("api_key", ["", None])
def test_chat_json_without_api_key_returns_none_without_client(
    monkeypatch, api_key
):
    _patch_settings(
        monkeypatch,
        api_key=api_key,
        model="primary-model",
        fallbacks="fallback-model",
    )
    make_client_calls = []
    monkeypatch.setattr(
        llm_client,
        "_make_client",
        lambda: make_client_calls.append(True),
    )

    assert chat_json("Extract the claim.") is None
    assert make_client_calls == []


def test_chat_json_falls_back_after_invalid_json(monkeypatch):
    _patch_settings(
        monkeypatch,
        api_key="test-key",
        model="primary-model",
        fallbacks="fallback-model",
    )

    def handler(kwargs):
        if kwargs["model"] == "primary-model":
            return _response("Sorry, I cannot produce JSON today.", model="primary-model")
        return _response(
            '```json\n{"answer": "from fallback", "valid": true}\n```',
            model="fallback-model",
        )

    client, completions = _fake_client(handler)
    monkeypatch.setattr(llm_client, "_make_client", lambda: client)

    result = chat_json("Extract the claim.")

    assert result == ({"answer": "from fallback", "valid": True}, "fallback-model")
    assert [call["model"] for call in completions.calls] == [
        "primary-model",
        "fallback-model",
    ]
    assert all(call["stream"] is False for call in completions.calls)