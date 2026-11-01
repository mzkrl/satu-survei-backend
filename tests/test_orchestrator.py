from __future__ import annotations

import json

import pytest

from apps.agents.llm import LLMProviderError, LLMResponse
from apps.pipeline.orchestrator import build_cache_payload, run_pipeline, save_demo_cache
from apps.surveys.models import (
    AnalysisResult,
    EvidenceRecord,
    PipelineAttempt,
    RuleResult,
    Survey,
    SurveyProfile,
)

from tests.conftest import PAGE_ONE_TEXT, make_analysis_json, make_normalization_json

pytestmark = pytest.mark.django_db

NORM_JSON = make_normalization_json()
ANALYSIS_JSON = make_analysis_json()


def _survey(survey_factory, pdf_factory, **kwargs) -> Survey:
    return survey_factory(content=pdf_factory(text=PAGE_ONE_TEXT), **kwargs)


def _make_mock_orchestrator_client(responses: list[str | Exception] | None = None):
    """Mock kustom untuk run_pipeline tanpa memanggil API asli."""
    responses = list(responses) if responses else []
    index = 0

    def complete(system: str, user: str, timeout_s: int):
        nonlocal index
        index += 1
        if index > len(responses):
            raise Exception("Mock: respons habis")
        item = responses[index - 1]
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model="mock-model", latency_ms=1)

    return type("_OrchestratorMock", (), {"complete": complete})()


def test_happy_path_completes_with_all_artifacts(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client([NORM_JSON, ANALYSIS_JSON])
    result = run_pipeline(survey.pk, client=client)

    assert result.status == Survey.Status.COMPLETED
    assert result.error_reason == ""
    assert SurveyProfile.objects.filter(survey=result).exists()
    evidence = EvidenceRecord.objects.get(survey=result, key="E1")
    assert evidence.grounded is True
    assert evidence.value == 72.4
    assert RuleResult.objects.filter(survey=result).count() == 2
    analysis = AnalysisResult.objects.get(survey=result)
    assert analysis.summary
    stages = list(
        result.attempts.order_by("created_at").values_list("stage", "ok", flat=False)
    )
    assert stages == [
        (PipelineAttempt.Stage.NORMALIZATION, True),
        (PipelineAttempt.Stage.ANALYSIS, True),
    ]
    assert result.llm_model == "mock-model"
    assert result.prompt_version == "analysis_v1"
    assert result.schema_version == "1.0"
    assert result.total_attempts == 2


def test_normalization_retry_then_success(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client(["rusak", NORM_JSON, ANALYSIS_JSON])
    result = run_pipeline(survey.pk, client=client)
    assert result.status == Survey.Status.COMPLETED
    norm_attempts = result.attempts.filter(stage=PipelineAttempt.Stage.NORMALIZATION)
    assert norm_attempts.count() == 2
    assert norm_attempts.filter(ok=False).count() == 1


def test_normalization_exhausted_marks_failed(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client(["rusak", "rusak", "rusak"])
    result = run_pipeline(survey.pk, client=client)
    assert result.status == Survey.Status.FAILED_NORMALIZATION
    assert result.error_stage == "normalization"
    assert "JSON tidak valid" in result.error_reason
    assert result.attempts.filter(stage=PipelineAttempt.Stage.NORMALIZATION).count() == 3
    assert not SurveyProfile.objects.filter(survey=result).exists()


def test_analysis_exhausted_marks_failed_but_keeps_evidence(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client([NORM_JSON, "rusak", "rusak", "rusak"])
    result = run_pipeline(survey.pk, client=client)
    assert result.status == Survey.Status.FAILED_ANALYSIS
    assert result.error_stage == "analysis"
    assert EvidenceRecord.objects.filter(survey=result).exists()
    assert RuleResult.objects.filter(survey=result).count() == 2
    assert not AnalysisResult.objects.filter(survey=result).exists()


def test_provider_error_marks_failed_system(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client([LLMProviderError("Provider LLM gagal: APITimeoutError")])
    result = run_pipeline(survey.pk, client=client)
    assert result.status == Survey.Status.FAILED_SYSTEM
    assert result.error_stage == "system"
    assert "Provider LLM" in result.error_reason


def test_unexpected_exception_marks_failed_system(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)

    class BoomClient:
        def complete(self, *, system: str, user: str, timeout_s: int):
            raise RuntimeError("detail internal")

    result = run_pipeline(survey.pk, client=BoomClient())
    assert result.status == Survey.Status.FAILED_SYSTEM
    assert "tak terduga" in result.error_reason
    assert "detail internal" not in result.error_reason


def test_blank_pdf_rejected_during_extraction(survey_factory, pdf_factory) -> None:
    survey = survey_factory(content=pdf_factory(text=""))
    client = _make_mock_orchestrator_client([NORM_JSON, ANALYSIS_JSON])
    result = run_pipeline(survey.pk, client=client)
    assert result.status == Survey.Status.REJECTED_FILE
    assert result.error_stage == "extraction"
    assert result.attempts.count() == 0


def test_rerun_completed_survey_is_noop(survey_factory, pdf_factory) -> None:
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client([NORM_JSON, ANALYSIS_JSON])
    first = run_pipeline(survey.pk, client=client)
    assert first.status == Survey.Status.COMPLETED
    second = run_pipeline(survey.pk, client=_make_mock_orchestrator_client([]))
    assert second.status == Survey.Status.COMPLETED
    assert second.attempts.count() == 2


def test_demo_cache_loads_without_llm(survey_factory, pdf_factory, settings, tmp_path) -> None:
    settings.DEMO_MODE = True
    settings.DEMO_CACHE_DIR = tmp_path
    survey = _survey(survey_factory, pdf_factory)
    cache = {
        "schema_version": "1.0",
        "llm_model": "cached-model",
        "prompt_version": "analysis_v1",
        "normalization": json.loads(NORM_JSON),
        "analysis": json.loads(ANALYSIS_JSON),
        "grounding": {"E1": True},
    }
    (tmp_path / f"{survey.file_sha256}.json").write_text(
        json.dumps(cache), encoding="utf-8"
    )
    # Tanpa client (tanpa LLM) - demo mode melewati LLM total
    result = run_pipeline(survey.pk)
    assert result.status == Survey.Status.COMPLETED
    assert result.llm_model == "cached-model"
    assert EvidenceRecord.objects.get(survey=result, key="E1").grounded is True
    assert AnalysisResult.objects.filter(survey=result).exists()


def test_cache_roundtrip(survey_factory, pdf_factory, settings, tmp_path) -> None:
    settings.DEMO_CACHE_DIR = tmp_path
    survey = _survey(survey_factory, pdf_factory)
    client = _make_mock_orchestrator_client([NORM_JSON, ANALYSIS_JSON])
    run_pipeline(survey.pk, client=client)

    survey.refresh_from_db()
    path = save_demo_cache(survey)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["normalization"]["evidence_records"][0]["id"] == "E1"
    assert payload["analysis"]["summary"]
    assert build_cache_payload(survey)["grounding"]["E1"] is True