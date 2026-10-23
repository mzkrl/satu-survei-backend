from __future__ import annotations

import pytest

from apps.pipeline.pdf_text import (
    SCAN_MESSAGE,
    TOO_LONG_MESSAGE,
    check_text_limits,
    extract_pages,
    extract_text_for_survey,
    format_pages_for_llm,
    format_survey_for_llm,
)
from apps.surveys.models import PageText, Survey

pytestmark = pytest.mark.django_db


def test_extract_pages_returns_page_numbers_and_text(pdf_factory) -> None:
    pages = extract_pages(pdf_factory(pages=3, text="Isi laporan survei."))
    assert [no for no, _ in pages] == [1, 2, 3]
    assert all("Isi laporan survei." in text for _, text in pages)


def test_extract_pages_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        extract_pages(b"%PDF-1.4\nbukan pdf sungguhan")


def test_format_pages_for_llm() -> None:
    formatted = format_pages_for_llm([(1, "abc"), (2, "def")])
    assert formatted == "=== PAGE 1 ===\nabc\n\n=== PAGE 2 ===\ndef"


def test_check_text_limits_ok() -> None:
    pages = [(1, "x" * 500)]
    assert check_text_limits(pages, min_chars_per_page=200, max_text_chars=1000) == []


def test_check_text_limits_flags_blank_pdf_as_scan() -> None:
    pages = [(1, ""), (2, "")]
    errors = check_text_limits(pages, min_chars_per_page=200, max_text_chars=100000)
    assert SCAN_MESSAGE in errors


def test_check_text_limits_flags_too_long() -> None:
    pages = [(1, "x" * 2000)]
    errors = check_text_limits(pages, min_chars_per_page=10, max_text_chars=1000)
    assert TOO_LONG_MESSAGE in errors


def test_check_text_limits_empty_pages() -> None:
    assert check_text_limits([], min_chars_per_page=1, max_text_chars=10) == [
        "PDF tidak berisi halaman."
    ]


def test_extract_text_for_survey_stores_page_texts(survey_factory, pdf_factory, settings) -> None:
    settings.MIN_CHARS_PER_PAGE = 1
    survey = survey_factory(content=pdf_factory(pages=2, text="Isi laporan survei yang cukup."))
    ok = extract_text_for_survey(survey)
    assert ok is True
    assert survey.status == Survey.Status.PENDING
    assert list(survey.pages.order_by("page_no").values_list("page_no", flat=True)) == [1, 2]


def test_extract_text_for_survey_is_idempotent(survey_factory, pdf_factory, settings) -> None:
    settings.MIN_CHARS_PER_PAGE = 1
    survey = survey_factory(content=pdf_factory(text="Isi laporan survei yang cukup."))
    assert extract_text_for_survey(survey) is True
    assert extract_text_for_survey(survey) is True
    assert PageText.objects.filter(survey=survey).count() == 1


def test_format_survey_for_llm_uses_page_markers(survey_factory, pdf_factory, settings) -> None:
    settings.MIN_CHARS_PER_PAGE = 1
    survey = survey_factory(content=pdf_factory(text="Isi laporan survei yang cukup."))
    assert extract_text_for_survey(survey) is True
    formatted = format_survey_for_llm(survey)
    assert formatted.startswith("=== PAGE 1 ===")
    assert "Isi laporan survei yang cukup." in formatted


def test_blank_pdf_rejected_with_scan_message(survey_factory, pdf_factory) -> None:
    survey = survey_factory(content=pdf_factory(text=""))
    ok = extract_text_for_survey(survey)
    assert ok is False
    survey.refresh_from_db()
    assert survey.status == Survey.Status.REJECTED_FILE
    assert survey.error_stage == "extraction"
    assert SCAN_MESSAGE in survey.error_reason
    assert not survey.pages.exists()


def test_too_long_pdf_rejected(survey_factory, pdf_factory, settings) -> None:
    settings.MIN_CHARS_PER_PAGE = 1
    settings.MAX_TEXT_CHARS = 10
    survey = survey_factory(content=pdf_factory(text="Isi laporan survei yang cukup."))
    ok = extract_text_for_survey(survey)
    assert ok is False
    survey.refresh_from_db()
    assert survey.status == Survey.Status.REJECTED_FILE
    assert TOO_LONG_MESSAGE in survey.error_reason


def test_corrupt_pdf_rejected(survey_factory) -> None:
    survey = survey_factory(content=b"%PDF-1.4\nbukan pdf sungguhan")
    ok = extract_text_for_survey(survey)
    assert ok is False
    survey.refresh_from_db()
    assert survey.status == Survey.Status.REJECTED_FILE
    assert "tidak dapat dibuka" in survey.error_reason
