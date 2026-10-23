from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.pipeline.orchestrator import SCHEMA_VERSION
from apps.surveys.models import Survey

SURVEY_FIELDS = [
    "id",
    "title",
    "publisher",
    "publication_date",
    "period_start",
    "period_end",
    "source_url",
    "notes",
    "status",
    "page_count",
    "created_at",
]


class SurveyListSerializer(serializers.ModelSerializer):
    disclosure_score = serializers.SerializerMethodField()
    moe_status = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = SURVEY_FIELDS + ["disclosure_score", "moe_status"]

    def _rule(self, obj: Survey, rule_id: str):
        for rule in obj.rule_results.all():
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_disclosure_score(self, obj: Survey) -> int | None:
        rule = self._rule(obj, "R2")
        if rule is None:
            return None
        return rule.details.get("score")

    def get_moe_status(self, obj: Survey) -> str | None:
        rule = self._rule(obj, "R1")
        return rule.status if rule else None


def build_detail_payload(survey: Survey) -> dict[str, Any]:
    profile = getattr(survey, "profile", None)
    analysis = getattr(survey, "analysis", None)
    evidence = [
        {
            "key": record.key,
            "label_original": record.label_original,
            "label_normalized": record.label_normalized,
            "value": record.value,
            "value_raw": record.value_raw,
            "unit": record.unit,
            "period": record.period,
            "geography": record.geography,
            "definition": record.definition,
            "source_page": record.source_page,
            "source_excerpt": record.source_excerpt,
            "unknown_fields": list(record.unknown_fields),
            "grounded": record.grounded,
        }
        for record in survey.evidence.order_by("key")
    ]
    rules = [
        {
            "rule_id": rule.rule_id,
            "status": rule.status,
            "title": rule.title,
            "message": rule.message,
            "details": rule.details,
        }
        for rule in survey.rule_results.order_by("rule_id")
    ]
    return {
        "schema_version": survey.schema_version or SCHEMA_VERSION,
        "survey": {
            field: getattr(survey, field) for field in SURVEY_FIELDS if field != "id"
        } | {"id": survey.pk, "file_sha256": survey.file_sha256},
        "profile": profile.data if profile else None,
        "evidence": evidence,
        "rules": rules,
        "analysis": (
            {
                "summary": analysis.summary,
                "findings": analysis.findings,
                "caveats": analysis.caveats,
                "visualizations": analysis.visualizations,
            }
            if analysis
            else None
        ),
        "provenance": {
            "llm_model": survey.llm_model,
            "prompt_version": survey.prompt_version,
            "schema_version": survey.schema_version or SCHEMA_VERSION,
            "total_attempts": survey.total_attempts,
            "file_sha256": survey.file_sha256,
        },
    }
