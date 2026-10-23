from __future__ import annotations

import math

import pytest

from apps.agents.schemas import NormalizationOutput
from apps.rules.disclosure import ProfileInfo, evaluate_disclosure
from apps.rules.engine import run_rules, save_rule_results
from apps.rules.moe import compute_expected_moe, evaluate_moe, is_non_probability, z_for_confidence
from apps.surveys.models import RuleResult

from tests.conftest import make_normalization_output


def _moe(**overrides):
    defaults = {
        "sample_size": 1200.0,
        "moe_claimed_pct": 2.9,
        "confidence_level_pct": 95.0,
        "sampling_method": "multistage random sampling",
    }
    defaults.update(overrides)
    return evaluate_moe(**defaults)


def test_z_values() -> None:
    assert z_for_confidence(95) == 1.96
    assert z_for_confidence(90) == 1.645
    assert z_for_confidence(99) == 2.576


def test_expected_moe_n1200_95() -> None:
    expected = compute_expected_moe(1200, 1.96)
    assert math.isclose(expected, 2.83, abs_tol=0.01)


def test_moe_claim_within_tolerance_passes() -> None:
    outcome = _moe()
    assert outcome.status == "pass"
    assert outcome.details["n"] == 1200.0
    assert outcome.details["z"] == 1.96
    assert math.isclose(outcome.details["moe_expected"], 2.83, abs_tol=0.01)
    assert outcome.details["moe_claimed"] == 2.9
    assert "SRS" in outcome.details["asumsi"]


def test_moe_claim_larger_passes_with_design_effect_note() -> None:
    outcome = _moe(moe_claimed_pct=4.5)
    assert outcome.status == "pass"
    assert "design effect" in outcome.message


def test_moe_claim_smaller_fails() -> None:
    outcome = _moe(moe_claimed_pct=1.5)
    assert outcome.status == "fail"
    assert "lebih kecil" in outcome.message


def test_moe_missing_n_is_na() -> None:
    outcome = _moe(sample_size=None)
    assert outcome.status == "na"
    assert "ukuran sampel" in outcome.message


def test_moe_missing_claim_is_na() -> None:
    outcome = _moe(moe_claimed_pct=None)
    assert outcome.status == "na"
    assert "klaim margin of error" in outcome.message


def test_moe_missing_confidence_assumes_95() -> None:
    outcome = _moe(confidence_level_pct=None)
    assert outcome.status == "pass"
    assert outcome.details["z"] == 1.96
    assert "diasumsikan 95%" in outcome.details["asumsi"]


def test_moe_non_probability_method_warns() -> None:
    for method in ("kuota", "online panel", "convenience sampling", "snowball"):
        outcome = _moe(sampling_method=method)
        assert outcome.status == "warn", method
        assert "non-probabilitas" in outcome.message


def test_is_non_probability_detects_keywords() -> None:
    assert is_non_probability("Quota sampling")
    assert not is_non_probability("multistage random sampling")


def test_moe_confidence_90() -> None:
    outcome = _moe(confidence_level_pct=90.0, moe_claimed_pct=2.37)
    assert outcome.details["z"] == 1.645
    assert math.isclose(outcome.details["moe_expected"], 2.37, abs_tol=0.01)


def _disclosure_profile(**overrides) -> dict[str, ProfileInfo]:
    found = ProfileInfo(found=True, page=4, excerpt="kutipan")
    missing = ProfileInfo(found=False)
    profile = {
        "sampling_method": found,
        "sample_size": found,
        "fieldwork_start": found,
        "fieldwork_end": found,
        "sponsor_or_funder": found,
        "population": found,
        "question_wording_disclosed": found,
        "mode": found,
        "moe_claimed_pct": found,
        "confidence_level_pct": found,
        "weighting": found,
    }
    profile.update(overrides)
    return profile


def test_disclosure_full_score_passes() -> None:
    outcome = evaluate_disclosure(_disclosure_profile())
    assert outcome.status == "pass"
    assert outcome.details["score"] == 9
    assert outcome.details["total"] == 9
    assert "Semua 9 butir" in outcome.message


def test_disclosure_six_of_nine_warns() -> None:
    outcome = evaluate_disclosure(
        _disclosure_profile(
            sponsor_or_funder=ProfileInfo(found=False),
            weighting=ProfileInfo(found=False),
            question_wording_disclosed=ProfileInfo(found=False),
        )
    )
    assert outcome.status == "warn"
    assert outcome.details["score"] == 6
    assert "Pendana / pemberi mandat" in outcome.message
    assert "Tidak ditemukan di dokumen" in outcome.message


def test_disclosure_three_of_nine_fails() -> None:
    outcome = evaluate_disclosure(
        _disclosure_profile(
            sampling_method=ProfileInfo(found=False),
            sample_size=ProfileInfo(found=False),
            fieldwork_start=ProfileInfo(found=False),
            fieldwork_end=ProfileInfo(found=False),
            sponsor_or_funder=ProfileInfo(found=False),
            weighting=ProfileInfo(found=False),
            question_wording_disclosed=ProfileInfo(found=False),
        )
    )
    assert outcome.status == "fail"
    assert outcome.details["score"] == 3


def test_disclosure_fieldwork_requires_both_dates() -> None:
    outcome = evaluate_disclosure(
        _disclosure_profile(fieldwork_end=ProfileInfo(found=False))
    )
    fieldwork_item = next(i for i in outcome.details["items"] if i["item"] == "fieldwork")
    assert fieldwork_item["found"] is False
    assert outcome.details["score"] == 8


def test_disclosure_moe_item_requires_both_claim_and_confidence() -> None:
    outcome = evaluate_disclosure(
        _disclosure_profile(confidence_level_pct=ProfileInfo(found=False))
    )
    moe_item = next(i for i in outcome.details["items"] if i["item"] == "moe_confidence")
    assert moe_item["found"] is False


@pytest.mark.django_db
def test_run_rules_on_normalized_profile() -> None:
    parsed = NormalizationOutput.model_validate(make_normalization_output())
    outcomes = run_rules(parsed.survey_profile)
    assert [o.rule_id for o in outcomes] == ["R1", "R2"]
    assert outcomes[0].status == "pass"
    assert outcomes[1].status == "warn"
    assert outcomes[1].details["score"] == 5


@pytest.mark.django_db
def test_save_rule_results_is_idempotent(survey_factory) -> None:
    parsed = NormalizationOutput.model_validate(make_normalization_output())
    survey = survey_factory()
    outcomes = run_rules(parsed.survey_profile)
    save_rule_results(survey, outcomes)
    save_rule_results(survey, outcomes)
    assert RuleResult.objects.filter(survey=survey).count() == 2
    r1 = RuleResult.objects.get(survey=survey, rule_id="R1")
    assert r1.status == "pass"
    assert r1.details["n"] == 1200.0
