from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from apps.agents.analysis import analyze_with_retries
from apps.agents.llm import LLMProviderError, LLMResponse
from apps.agents.schemas import AnalysisOutput
from apps.pipeline.qc import run_analysis_qc

from tests.conftest import make_analysis_json, make_analysis_output

VALID_EVIDENCE_IDS = {"E1"}
EVIDENCE_VALUES = {"E1": 72.4}
VALID_RULE_IDS = {"R1", "R2"}
RULE_STATUSES = {"pass", "warn"}

VALID_JSON = make_analysis_json()


def _qc(raw_text: str, **overrides):
    params = {
        "valid_evidence_ids": VALID_EVIDENCE_IDS,
        "evidence_values": EVIDENCE_VALUES,
        "valid_rule_ids": VALID_RULE_IDS,
        "rule_statuses": RULE_STATUSES,
    }
    params.update(overrides)
    return run_analysis_qc(raw_text, **params)


# -- Helper kustom: Mock LLM client untuk tes --
class _MockLLMClient:
    """Mock LLM client untuk tes yang mirip LLM client."""

    def __init__(self, responses: list[str | Exception] | None = None):
        self._responses = list(responses) if responses else []
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

    def queue(self, *responses: str | Exception) -> None:
        self._responses.extend(responses)


# -- Tes --


def test_analysis_schema_valid() -> None:
    parsed = AnalysisOutput.model_validate(make_analysis_output())
    assert parsed.summary
    assert parsed.visualizations[0].data[0].value == 72.4


def test_analysis_schema_requires_findings() -> None:
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(findings=[]))


def test_analysis_schema_limits_findings_to_eight() -> None:
    findings = [
        {"text": f"temuan {i}", "evidence_ids": ["E1"], "rule_ids": []} for i in range(9)
    ]
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(findings=findings))


def test_analysis_schema_rejects_unknown_chart_type() -> None:
    viz = [{"id": "V1", "type": "pie", "title": "x", "evidence_ids": ["E1"]}]
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(visualizations=viz))


def test_analysis_schema_limits_visualizations_to_four() -> None:
    vizzes = [
        {"id": f"V1", "type": "metric_table", "title": f"t{i}", "evidence_ids": ["E1"]}
        for i in range(1, 6)
    ]
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(visualizations=vizzes))


def test_analysis_schema_metric_bar_requires_data() -> None:
    viz = [{"id": "V1", "type": "metric_bar", "title": "x", "data": []}]
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(visualizations=viz))


def test_analysis_schema_metric_table_requires_evidence_ids() -> None:
    viz = [{"id": "V1", "type": "metric_table", "title": "x", "evidence_ids": []}]
    with pytest.raises(Exception):
        AnalysisOutput.model_validate(make_analysis_output(visualizations=viz))


def test_analysis_qc_valid_passes() -> None:
    result = _qc(VALID_JSON)
    assert result.ok is True
    assert result.errors == []
    assert isinstance(result.parsed, AnalysisOutput)


def test_analysis_qc_tolerates_code_fence() -> None:
    assert _qc(f"```json\n{VALID_JSON}\n```").ok is True


def test_analysis_qc_parse_error() -> None:
    result = _qc("bukan json")
    assert result.ok is False
    assert any(e.startswith("JSON tidak valid") for e in result.errors)


def test_analysis_qc_unknown_evidence_id() -> None:
    output = make_analysis_output()
    output["findings"][0]["evidence_ids"] = ["E9"]
    result = _qc(json.dumps(output))
    assert result.ok is False
    assert any("E9" in e and "tidak ada di bukti survei" in e for e in result.errors)


def test_analysis_qc_unknown_rule_id() -> None:
    output = make_analysis_output()
    output["caveats"][0]["rule_ids"] = ["R9"]
    result = _qc(json.dumps(output))
    assert result.ok is False
    assert any("R9" in e and "tidak ada di hasil Rule Engine" in e for e in result.errors)


def test_analysis_qc_chart_value_mismatch() -> None:
    output = make_analysis_output()
    output["visualizations"][0]["data"][0]["value"] = 80.0
    result = _qc(json.dumps(output))
    assert result.ok is False
    assert any("tidak sama dengan" in e for e in result.errors)


def test_analysis_qc_chart_value_match_passes() -> None:
    output = make_analysis_output()
    output["visualizations"][0]["data"][0]["value"] = 72.4
    assert _qc(json.dumps(output)).ok is True


def test_analysis_qc_chart_on_non_numeric_evidence() -> None:
    result = _qc(json.dumps(make_analysis_output()), evidence_values={"E1": None})
    assert result.ok is False
    assert any("tidak bernilai numerik" in e for e in result.errors)


def test_analysis_qc_requires_caveats_when_rules_warn() -> None:
    output = make_analysis_output(caveats=[])
    result = _qc(json.dumps(output))
    assert result.ok is False
    assert any("caveats wajib" in e for e in result.errors)


def test_analysis_qc_caveats_optional_when_rules_all_pass() -> None:
    output = make_analysis_output(caveats=[])
    assert _qc(json.dumps(output), rule_statuses={"pass"}).ok is True


def test_analyze_happy_path() -> None:
    client = _MockLLMClient([VALID_JSON])
    outcome = _analyze(client)
    assert outcome.parsed is not None
    assert len(outcome.attempts) == 1
    assert outcome.errors == []


def test_analyze_retry_after_parse_error() -> None:
    client = _MockLLMClient(["rusak", VALID_JSON])
    outcome = _analyze(client)
    assert outcome.parsed is not None
    assert len(outcome.attempts) == 2
    assert "JSON tidak valid" in client.calls[1]["user"]
    assert "Output sebelumnya" in client.calls[1]["user"]  # user field contains raw text


def test_analyze_retry_after_reference_error_excludes_raw() -> None:
    bad_output = make_analysis_output()
    bad_output["findings"][0]["evidence_ids"] = ["E9"]
    client = _MockLLMClient([json.dumps(bad_output), VALID_JSON])
    outcome = _analyze(client)
    assert outcome.parsed is not None
    retry_user = client.calls[1]["user"]
    assert "E9" in retry_user
    assert "Output sebelumnya" not in retry_user


def test_analyze_all_attempts_fail() -> None:
    client = _MockLLMClient(["rusak", "rusak", "rusak"])
    outcome = _analyze(client, max_attempts=3)
    assert outcome.parsed is None
    assert len(outcome.attempts) == 3
    assert outcome.errors


def test_analyze_provider_error_propagates() -> None:
    client = _MockLLMClient([LLMProviderError("provider mati")])
    with pytest.raises(LLMProviderError):
        _analyze(client)