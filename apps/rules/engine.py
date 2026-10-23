from __future__ import annotations

from typing import Iterable

from apps.agents.schemas import PROFILE_KEYS, SurveyProfileModel
from apps.rules.disclosure import ProfileInfo, evaluate_disclosure
from apps.rules.moe import evaluate_moe
from apps.rules.types import RuleOutcome
from apps.surveys.models import RuleResult, Survey


def extract_profile_infos(profile: SurveyProfileModel) -> dict[str, ProfileInfo]:
    infos: dict[str, ProfileInfo] = {}
    for key in PROFILE_KEYS:
        field = getattr(profile, key)
        infos[key] = ProfileInfo(
            found=field.status == "found",
            page=field.source.page if field.source else None,
            excerpt=field.source.excerpt if field.source else None,
        )
    return infos


def extract_moe_inputs(profile: SurveyProfileModel) -> dict:
    def value_of(key: str):
        field = getattr(profile, key)
        return field.value if field.status == "found" else None

    return {
        "sample_size": value_of("sample_size"),
        "moe_claimed_pct": value_of("moe_claimed_pct"),
        "confidence_level_pct": value_of("confidence_level_pct"),
        "sampling_method": value_of("sampling_method"),
    }


def run_rules(profile: SurveyProfileModel) -> list[RuleOutcome]:
    return [
        evaluate_moe(**extract_moe_inputs(profile)),
        evaluate_disclosure(extract_profile_infos(profile)),
    ]


def save_rule_results(survey: Survey, outcomes: Iterable[RuleOutcome]) -> list[RuleResult]:
    results: list[RuleResult] = []
    for outcome in outcomes:
        result, _ = RuleResult.objects.update_or_create(
            survey=survey,
            rule_id=outcome.rule_id,
            defaults={
                "status": outcome.status,
                "title": outcome.title,
                "message": outcome.message,
                "details": outcome.details,
            },
        )
        results.append(result)
    return results
