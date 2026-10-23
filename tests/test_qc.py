from __future__ import annotations

import json

import pytest

from apps.agents.schemas import NormalizationOutput
from apps.pipeline.qc import run_normalization_qc, strip_code_fence

from tests.conftest import make_normalization_output


def _qc(raw_text: str, pages: dict[int, str], min_ratio: float = 0.6):
    return run_normalization_qc(raw_text, pages=pages, grounding_min_ratio=min_ratio)


def test_strip_code_fence() -> None:
    fenced = '```json\n{"a": 1}\n```'
    assert strip_code_fence(fenced) == '{"a": 1}'


def test_valid_output_passes(normalization_pages) -> None:
    result = _qc(json.dumps(make_normalization_output()), normalization_pages)
    assert result.ok is True
    assert result.errors == []
    assert isinstance(result.parsed, NormalizationOutput)
    assert all(result.grounding.values())
    assert result.grounding["E1"] is True
    assert result.grounding["sample_size"] is True


def test_code_fenced_output_passes(normalization_pages) -> None:
    raw = f"```json\n{json.dumps(make_normalization_output())}\n```"
    assert _qc(raw, normalization_pages).ok is True


def test_broken_json_reports_parse_error(normalization_pages) -> None:
    result = _qc("bukan json sama sekali", normalization_pages)
    assert result.ok is False
    assert any(error.startswith("JSON tidak valid") for error in result.errors)


def test_missing_profile_key_names_field(normalization_pages) -> None:
    output = make_normalization_output()
    del output["survey_profile"]["sample_size"]
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False
    assert any("survey_profile.sample_size" in error for error in result.errors)


def test_found_without_source_names_field(normalization_pages) -> None:
    output = make_normalization_output()
    output["survey_profile"]["sample_size"]["source"] = None
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False
    assert any("survey_profile.sample_size" in error for error in result.errors)


def test_unknown_with_value_rejected(normalization_pages) -> None:
    output = make_normalization_output()
    output["survey_profile"]["weighting"] = {
        "status": "unknown",
        "value": "dibobot",
        "source": None,
    }
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False
    assert any("survey_profile.weighting" in error for error in result.errors)


def test_bad_evidence_id_format(normalization_pages) -> None:
    output = make_normalization_output()
    output["evidence_records"][0]["id"] = "X1"
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False
    assert any("evidence_records.0.id" in error for error in result.errors)


def test_duplicate_evidence_ids(normalization_pages) -> None:
    output = make_normalization_output()
    record = dict(output["evidence_records"][0])
    output["evidence_records"].append(record)
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False
    assert any("duplikat" in error for error in result.errors)


def test_empty_evidence_rejected(normalization_pages) -> None:
    output = make_normalization_output()
    output["evidence_records"] = []
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is False


def test_fake_excerpt_fails_grounding_ratio() -> None:
    pages = {1: "Teks halaman tanpa kutipan apa pun."}
    output = make_normalization_output(
        profile_excerpt="kutipan karangan yang tidak ada",
        evidence_excerpt="kutipan karangan yang juga tidak ada",
    )
    result = _qc(json.dumps(output), pages)
    assert result.ok is False
    assert any("kutipan tidak terverifikasi" in error for error in result.errors)


def test_single_fake_excerpt_kept_but_flagged(normalization_pages) -> None:
    output = make_normalization_output(evidence_excerpt="kutipan karangan E1")
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is True
    assert result.grounding["E1"] is False


def test_numeric_mismatch_flags_grounding(normalization_pages) -> None:
    output = make_normalization_output()
    output["evidence_records"][0]["value"] = 99.9
    result = _qc(json.dumps(output), normalization_pages)
    assert result.grounding["E1"] is False


def test_indonesian_number_format_passes_numeric_check(normalization_pages) -> None:
    output = make_normalization_output()
    output["survey_profile"]["sample_size"]["value"] = 1200
    result = _qc(json.dumps(output), normalization_pages)
    assert result.ok is True
    assert result.grounding["sample_size"] is True
