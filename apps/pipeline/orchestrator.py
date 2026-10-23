from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.agents.analysis import AnalysisAttempt, analyze_with_retries
from apps.agents.llm import LLMClient, LLMProviderError, get_llm_client
from apps.agents.normalization import NormalizationAttempt, normalize_with_retries
from apps.agents.schemas import AnalysisOutput, NormalizationOutput
from apps.pipeline.pdf_text import extract_text_for_survey, format_survey_for_llm
from apps.rules.engine import run_rules, save_rule_results
from apps.rules.types import RuleOutcome
from apps.surveys.models import (
    AnalysisResult,
    EvidenceRecord,
    PipelineAttempt,
    Survey,
    SurveyProfile,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

_FAILED_STATUS_BY_STAGE = {
    "extraction": Survey.Status.REJECTED_FILE,
    "normalization": Survey.Status.FAILED_NORMALIZATION,
    "analysis": Survey.Status.FAILED_ANALYSIS,
    "system": Survey.Status.FAILED_SYSTEM,
}


def run_pipeline(survey_id: int, *, client: LLMClient | None = None) -> Survey:
    survey = Survey.objects.get(pk=survey_id)
    if survey.status not in (Survey.Status.PENDING, Survey.Status.PROCESSING):
        return survey

    survey.status = Survey.Status.PROCESSING
    survey.error_stage = ""
    survey.error_reason = ""
    survey.save(update_fields=["status", "error_stage", "error_reason"])

    try:
        _run_stages(survey, client=client)
    except LLMProviderError as exc:
        _mark_failed(survey, "system", f"Provider LLM gagal: {exc}")
    except TimeoutError as exc:
        _mark_failed(survey, "system", str(exc))
    except Exception:
        logger.exception("pipeline_unexpected survey_id=%s", survey_id)
        _mark_failed(survey, "system", "Kesalahan sistem tak terduga. Silakan coba lagi nanti.")
    return survey


def _run_stages(survey: Survey, *, client: LLMClient | None) -> None:
    if _try_load_cached(survey):
        return

    if not extract_text_for_survey(survey):
        return

    pages = dict(survey.pages.order_by("page_no").values_list("page_no", "text"))
    document_text = format_survey_for_llm(survey)
    llm_client = client if client is not None else get_llm_client()
    deadline = time.monotonic() + settings.PIPELINE_TOTAL_BUDGET_S

    normalization = normalize_with_retries(
        llm_client,
        document_text=document_text,
        pages=pages,
        max_attempts=settings.PIPELINE_MAX_RETRIES + 1,
        timeout_s=settings.LLM_TIMEOUT_S,
        grounding_min_ratio=settings.GROUNDING_MIN_RATIO,
        deadline=deadline,
    )
    _save_attempts(survey, PipelineAttempt.Stage.NORMALIZATION, normalization.attempts, "normalization_v1")
    _set_attempts_meta(survey, normalization.attempts)

    if normalization.parsed is None:
        reason = _join_errors("Ekstraksi bukti gagal setelah semua percobaan", normalization.errors)
        _mark_failed(survey, "normalization", reason)
        return

    _persist_normalization(survey, normalization.parsed, normalization.grounding)
    outcomes = run_rules(normalization.parsed.survey_profile)
    save_rule_results(survey, outcomes)

    analysis = analyze_with_retries(
        llm_client,
        title=survey.title,
        publisher=survey.publisher,
        evidence_rows=_evidence_rows(normalization.parsed),
        rule_rows=_rule_rows(outcomes),
        valid_evidence_ids={record.id for record in normalization.parsed.evidence_records},
        evidence_values={record.id: record.value for record in normalization.parsed.evidence_records},
        valid_rule_ids={outcome.rule_id for outcome in outcomes},
        rule_statuses={outcome.status for outcome in outcomes},
        max_attempts=settings.PIPELINE_MAX_RETRIES + 1,
        timeout_s=settings.LLM_TIMEOUT_S,
        deadline=deadline,
    )
    _save_attempts(survey, PipelineAttempt.Stage.ANALYSIS, analysis.attempts, "analysis_v1")
    _set_attempts_meta(survey, analysis.attempts)

    if analysis.parsed is None:
        reason = _join_errors("Narasi analisis gagal setelah semua percobaan", analysis.errors)
        _mark_failed(survey, "analysis", reason)
        return

    _persist_analysis(survey, analysis.parsed)
    survey.status = Survey.Status.COMPLETED
    survey.error_stage = ""
    survey.error_reason = ""
    survey.prompt_version = "analysis_v1"
    survey.schema_version = SCHEMA_VERSION
    survey.save(
        update_fields=[
            "status",
            "error_stage",
            "error_reason",
            "prompt_version",
            "schema_version",
        ]
    )


def _mark_failed(survey: Survey, stage: str, reason: str) -> None:
    survey.status = _FAILED_STATUS_BY_STAGE[stage]
    survey.error_stage = stage
    survey.error_reason = reason
    survey.save(update_fields=["status", "error_stage", "error_reason"])
    logger.info("pipeline_failed survey_id=%s stage=%s", survey.pk, stage)


def _join_errors(prefix: str, errors: list[str]) -> str:
    if not errors:
        return prefix
    return f"{prefix}: {'; '.join(errors)}"


def _save_attempts(
    survey: Survey,
    stage: str,
    attempts: list[NormalizationAttempt] | list[AnalysisAttempt],
    prompt_version: str,
) -> None:
    for attempt in attempts:
        PipelineAttempt.objects.create(
            survey=survey,
            stage=stage,
            attempt_no=attempt.attempt_no,
            ok=attempt.ok,
            error=attempt.error,
            latency_ms=attempt.latency_ms,
            model=attempt.model,
            prompt_version=prompt_version,
        )
        logger.info(
            "pipeline_attempt survey_id=%s stage=%s attempt=%s ok=%s",
            survey.pk,
            stage,
            attempt.attempt_no,
            attempt.ok,
        )


def _set_attempts_meta(
    survey: Survey,
    attempts: list[NormalizationAttempt] | list[AnalysisAttempt],
) -> None:
    survey.total_attempts = (survey.total_attempts or 0) + len(attempts)
    if attempts:
        survey.llm_model = attempts[-1].model
    survey.save(update_fields=["total_attempts", "llm_model"])


def _persist_normalization(
    survey: Survey,
    parsed: NormalizationOutput,
    grounding: dict[str, bool],
) -> None:
    SurveyProfile.objects.update_or_create(
        survey=survey,
        defaults={"data": parsed.survey_profile.model_dump()},
    )
    EvidenceRecord.objects.filter(survey=survey).delete()
    EvidenceRecord.objects.bulk_create(
        [
            EvidenceRecord(
                survey=survey,
                key=record.id,
                label_original=record.label_original,
                label_normalized=record.label_normalized,
                value=record.value,
                value_raw=record.value_raw,
                unit=record.unit,
                period=record.period,
                geography=record.geography,
                definition=record.definition or "",
                source_page=record.source.page,
                source_excerpt=record.source.excerpt,
                unknown_fields=list(record.unknown_fields),
                grounded=bool(grounding.get(record.id, False)),
            )
            for record in parsed.evidence_records
        ]
    )


def _persist_analysis(survey: Survey, analysis: AnalysisOutput) -> None:
    AnalysisResult.objects.update_or_create(
        survey=survey,
        defaults={
            "summary": analysis.summary,
            "findings": [item.model_dump() for item in analysis.findings],
            "caveats": [item.model_dump() for item in analysis.caveats],
            "visualizations": [item.model_dump() for item in analysis.visualizations],
        },
    )


def _evidence_rows(parsed: NormalizationOutput) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "label": record.label_original,
            "value": record.value,
            "unit": record.unit,
            "period": record.period,
        }
        for record in parsed.evidence_records
    ]


def _rule_rows(outcomes: list[RuleOutcome]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": outcome.rule_id,
            "status": outcome.status,
            "title": outcome.title,
            "message": outcome.message,
        }
        for outcome in outcomes
    ]


def demo_cache_path(survey: Survey) -> Path:
    return Path(settings.DEMO_CACHE_DIR) / f"{survey.file_sha256}.json"


def _try_load_cached(survey: Survey) -> bool:
    if not settings.DEMO_MODE:
        return False
    cache_path = demo_cache_path(survey)
    if not cache_path.is_file():
        return False

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    parsed = NormalizationOutput.model_validate(data["normalization"])
    analysis = AnalysisOutput.model_validate(data["analysis"])
    grounding = {key: bool(value) for key, value in data.get("grounding", {}).items()}

    _persist_normalization(survey, parsed, grounding)
    outcomes = run_rules(parsed.survey_profile)
    save_rule_results(survey, outcomes)
    _persist_analysis(survey, analysis)

    survey.prompt_version = str(data.get("prompt_version", "analysis_v1"))
    survey.llm_model = str(data.get("llm_model", "cache"))
    survey.schema_version = str(data.get("schema_version", SCHEMA_VERSION))
    survey.status = Survey.Status.COMPLETED
    survey.error_stage = ""
    survey.error_reason = ""
    survey.save(
        update_fields=[
            "prompt_version",
            "llm_model",
            "schema_version",
            "status",
            "error_stage",
            "error_reason",
        ]
    )
    logger.info("pipeline_cache_hit survey_id=%s", survey.pk)
    return True


def build_cache_payload(survey: Survey) -> dict[str, Any]:
    profile = survey.profile
    evidence = list(survey.evidence.order_by("key"))
    analysis = survey.analysis
    return {
        "schema_version": survey.schema_version or SCHEMA_VERSION,
        "llm_model": survey.llm_model,
        "prompt_version": survey.prompt_version or "analysis_v1",
        "normalization": {
            "survey_profile": profile.data,
            "evidence_records": [
                {
                    "id": record.key,
                    "label_original": record.label_original,
                    "label_normalized": record.label_normalized,
                    "value": record.value,
                    "value_raw": record.value_raw,
                    "unit": record.unit,
                    "period": record.period,
                    "geography": record.geography,
                    "definition": record.definition or None,
                    "source": {"page": record.source_page, "excerpt": record.source_excerpt},
                    "unknown_fields": list(record.unknown_fields),
                }
                for record in evidence
            ],
        },
        "grounding": {record.key: record.grounded for record in evidence},
        "analysis": {
            "summary": analysis.summary,
            "findings": analysis.findings,
            "caveats": analysis.caveats,
            "visualizations": analysis.visualizations,
        },
    }


def save_demo_cache(survey: Survey) -> Path:
    cache_path = demo_cache_path(survey)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(build_cache_payload(survey), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cache_path
