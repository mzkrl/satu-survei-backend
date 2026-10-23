from __future__ import annotations

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.surveys.forms import SurveyUploadForm
from apps.surveys.models import Survey
from apps.surveys.services import create_or_get_survey

pytestmark = pytest.mark.django_db


def _upload(content: bytes, name: str = "laporan.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _cleaned(valid_metadata: dict, content: bytes = b"", name: str = "laporan.pdf") -> dict:
    data = {**valid_metadata, "file": _upload(content, name)}
    form = SurveyUploadForm(data=data, files=data)
    assert form.is_valid(), form.errors
    return form.cleaned_data


def test_valid_upload_creates_pending_survey(valid_metadata, pdf_factory) -> None:
    content = pdf_factory()
    survey, created = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    assert created is True
    assert survey.status == Survey.Status.PENDING
    assert survey.page_count == 1
    assert survey.error_reason == ""
    assert survey.file


def test_upload_same_file_twice_is_idempotent(valid_metadata, pdf_factory) -> None:
    content = pdf_factory()
    first, created_first = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    second, created_second = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert Survey.objects.count() == 1


def test_invalid_metadata_rejected_with_all_errors(valid_metadata, pdf_factory) -> None:
    content = pdf_factory()
    bad = {
        **valid_metadata,
        "title": "",
        "period_start": date(2026, 6, 1),
        "period_end": date(2026, 1, 1),
    }
    survey, created = create_or_get_survey(
        cleaned_data=bad,
        uploaded_file=_upload(content),
    )
    assert created is True
    assert survey.status == Survey.Status.REJECTED_METADATA
    assert survey.error_stage == "metadata"
    assert "title" in survey.error_reason
    assert "period_start" in survey.error_reason
    assert not survey.file


def test_non_pdf_rejected_as_file(valid_metadata) -> None:
    content = b"isi teks biasa, bukan pdf"
    survey, _ = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content, name="laporan.pdf"),
        uploaded_file=_upload(content),
    )
    assert survey.status == Survey.Status.REJECTED_FILE
    assert survey.error_stage == "file"
    assert "PDF yang valid" in survey.error_reason


def test_corrupt_pdf_rejected_as_file(valid_metadata) -> None:
    content = b"%PDF-1.4\nbukan pdf sungguhan"
    survey, _ = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    assert survey.status == Survey.Status.REJECTED_FILE
    assert "tidak dapat dibuka" in survey.error_reason


def test_rejected_file_record_is_also_idempotent(valid_metadata) -> None:
    content = b"isi teks biasa, bukan pdf"
    first, _ = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    second, created_second = create_or_get_survey(
        cleaned_data=_cleaned(valid_metadata, content),
        uploaded_file=_upload(content),
    )
    assert created_second is False
    assert first.pk == second.pk
    assert Survey.objects.count() == 1


def test_form_requires_title_and_file(valid_metadata) -> None:
    data = {**valid_metadata, "title": ""}
    form = SurveyUploadForm(data=data, files={})
    assert not form.is_valid()
    assert "title" in form.errors
    assert "file" in form.errors
