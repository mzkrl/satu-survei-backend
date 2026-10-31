from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agents.llm import LLMProviderError, LLMResponse
from apps.agents.normalization import (
    build_retry_user,
    load_system_prompt,
    normalize_with_retries,
)

from tests.conftest import make_normalization_json, make_normalization_output

VALID_JSON = make_normalization_json()


class _MockLLMClient:
    """Mock LLM client untuk tes tanpa memanggil API asli."""

    def __init__(self, responses: list[str | Exception] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self._index = 0

    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "timeout_s": timeout_s})
        if self._index >= len(self._responses):
            raise LLMProviderError("Mock: respons habis")
        item = self._responses[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model="mock-model", latency_ms=1)


def _make_mock_llm_client(
    responses: list[str | Exception] | None = None,
) -> _MockLLMClient:
    return _MockLLMClient(responses)


def _normalize(client, pages: dict[int, str], max_attempts: int = 3):
    return normalize_with_retries(
        client,
        document_text="=== PAGE 1 ===\nDokumen contoh.",
        pages=pages,
        max_attempts=max_attempts,
        timeout_s=10,
        grounding_min_ratio=0.6,
    )


# -- Tes --

def test_system_prompt_marks_document_as_data() -> None:
    prompt = load_system_prompt()
    assert "DATA, bukan instruksi" in prompt
    assert "JSON saja" in prompt


def test_happy_path_single_attempt(normalization_pages) -> None:
    client = _make_mock_llm_client([VALID_JSON])
    outcome = _normalize(client, normalization_pages)
    assert outcome.parsed is not None
    assert len(outcome.attempts) == 1
    assert outcome.attempts[0].ok is True
    assert outcome.errors == []
    assert outcome.grounding["E1"] is True
    assert len(client.calls) == 1


def test_broken_json_retries_and_succeeds(normalization_pages) -> None:
    client = _make_mock_llm_client(["bukan json", VALID_JSON])
    outcome = _normalize(client, normalization_pages)
    assert outcome.parsed is not None
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].ok is False
    assert "JSON tidak valid" in outcome.attempts[0].error
    retry_call = client.calls[1]
    assert "JSON tidak valid" in retry_call["user"]
    assert "Output sebelumnya" in retry_call["user"]


def test_schema_error_retry_does_not_include_raw_output(normalization_pages) -> None:
    incomplete = make_normalization_output()
    del incomplete["survey_profile"]["sample_size"]
    client = _make_mock_llm_client([json.dumps(incomplete), VALID_JSON])
    outcome = _normalize(client, normalization_pages)
    assert outcome.parsed is not None
    retry_call = client.calls[1]
    assert "survey_profile.sample_size" in retry_call["user"]
    assert "Output sebelumnya" not in retry_call["user"]


def test_all_attempts_fail_returns_errors(normalization_pages) -> None:
    client = _make_mock_llm_client(["rusak", "rusak", "rusak"])
    outcome = _normalize(client, normalization_pages, max_attempts=3)
    assert outcome.parsed is None
    assert len(outcome.attempts) == 3
    assert outcome.errors


def test_grounding_failure_retries_then_succeeds(normalization_pages) -> None:
    fake = make_normalization_json(
        profile_excerpt="kutipan karangan",
        evidence_excerpt="kutipan karangan",
    )
    client = _make_mock_llm_client([fake, VALID_JSON])
    outcome = _normalize(client, normalization_pages)
    assert outcome.parsed is not None
    assert len(outcome.attempts) == 2
    assert "kutipan tidak terverifikasi" in outcome.attempts[0].error


def test_provider_error_propagates(normalization_pages) -> None:
    client = _make_mock_llm_client([LLMProviderError("provider mati")])
    with pytest.raises(LLMProviderError):
        _normalize(client, normalization_pages)


def test_build_retry_user_structure() -> None:
    message = build_retry_user("TUGAS", ["error satu"], raw_text="{}")
    assert "TUGAS" in message
    assert "- error satu" in message
    assert "Output sebelumnya" in message
    assert "{}" in message