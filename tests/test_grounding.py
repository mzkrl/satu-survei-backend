from __future__ import annotations

import pytest

from apps.pipeline.grounding import (
    GroundingTarget,
    check_excerpt,
    check_grounding,
    check_number_in_excerpt,
    normalize_number,
    normalize_text,
    numbers_in,
)


def test_normalize_text_lowercases_and_collapses_whitespace() -> None:
    assert normalize_text("Halo  \n Dunia") == "halo dunia"


def test_normalize_text_dehyphenates_line_breaks() -> None:
    assert normalize_text("margin of\n error") == "margin of error"
    assert normalize_text("multi-\nstage") == "multistage"


def test_normalize_text_unifies_quotes() -> None:
    assert normalize_text("\u201cquoted\u201d") == '"quoted"'


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.200", 1200.0),
        ("1,200", 1200.0),
        ("72,4%", 72.4),
        ("72.4", 72.4),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("95", 95.0),
        ("1.200 responden", 1200.0),
        ("0,5", 0.5),
        ("tanpa angka", None),
    ],
)
def test_normalize_number(raw: str, expected: float | None) -> None:
    assert normalize_number(raw) == expected


def test_numbers_in_mixed_formats() -> None:
    assert numbers_in("sampel 1.200 responden, moe 2,9 persen") == [1200.0, 2.9]


def test_check_excerpt_substring_case_insensitive() -> None:
    assert check_excerpt("Margin of Error 2,9 persen", "teks ... margin of error 2,9 persen ...")
    assert not check_excerpt("angka karangan 99,9", "margin of error 2,9 persen")


def test_check_excerpt_handles_hyphenation_and_spacing() -> None:
    page = "Sampel sebanyak 1.200\nresponden disebutkan."
    assert check_excerpt("1.200 responden", page)


def test_check_excerpt_fuzzy_fallback() -> None:
    page = "Survei nasional dengan sampel 1.200 responden pada Maret 2026."
    excerpt = "Survei nasional dengan sampel 1.200 responden pada Maret 2026a"
    assert check_excerpt(excerpt, page)


def test_check_number_in_excerpt_indonesian_format() -> None:
    assert check_number_in_excerpt(72.4, "sebesar 72,4 persen")
    assert check_number_in_excerpt(1200.0, "sampel 1.200 responden")
    assert not check_number_in_excerpt(72.5, "sebesar 72,4 persen")


def test_check_grounding_maps_keys() -> None:
    pages = {1: "Sampel sebanyak 1.200 responden. Kepuasan 72,4 persen."}
    targets = [
        GroundingTarget(key="sample_size", page=1, excerpt="Sampel sebanyak 1.200 responden", numeric_value=1200.0),
        GroundingTarget(key="E1", page=1, excerpt="Kepuasan 72,4 persen", numeric_value=72.4),
        GroundingTarget(key="E2", page=2, excerpt="halo"),
        GroundingTarget(key="E3", page=1, excerpt="Kepuasan 72,4 persen", numeric_value=99.9),
    ]
    assert check_grounding(targets, pages) == {
        "sample_size": True,
        "E1": True,
        "E2": False,
        "E3": False,
    }
