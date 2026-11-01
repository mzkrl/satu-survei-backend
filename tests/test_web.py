from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.agents.llm import LLMProviderError, LLMResponse
from apps.pipeline.orchestrator import run_pipeline
from apps.surveys.models import Survey
from tests.conftest import (
    PAGE_ONE_TEXT,
    make_analysis_json,
    make_normalization_json,
    make_pdf_bytes,
)

PDF_TEXT = PAGE_ONE_TEXT * 2


class _MockLLMClient:
    """Mock LLM client untuk tes tanpa memanggil API asli."""

    def __init__(self, responses: list[str | Exception] | None = None) -> None:
        self._responses = list(responses or [])

    def complete(self, *, system: str, user: str, timeout_s: int) -> LLMResponse:
        if not self._responses:
            raise LLMProviderError("Mock: respons habis")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model="mock-model", latency_ms=1)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="peneliti", password="rahasia123"
    )


def run_fake_pipeline(survey: Survey, responses: list[str]) -> Survey:
    with patch(
        "apps.pipeline.orchestrator.get_llm_client",
        return_value=_MockLLMClient(responses),
    ):
        run_pipeline(survey.pk)
    survey.refresh_from_db()
    return survey


@pytest.fixture
def completed_survey(survey_factory) -> Survey:
    survey = survey_factory(
        make_pdf_bytes(text=PDF_TEXT),
        status=Survey.Status.PENDING,
        title="Survei Kepuasan Publik",
    )
    survey = run_fake_pipeline(
        survey, [make_normalization_json(), make_analysis_json()]
    )
    assert survey.status == Survey.Status.COMPLETED, survey.error_reason
    return survey


class TestHome:
    def test_home_lists_completed(self, client, completed_survey):
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Survei Kepuasan Publik" in content
        assert "Rontgen survei baru" in content

    def test_home_empty_state(self, client, db):
        response = client.get("/")
        assert response.status_code == 200
        assert "Belum ada survei publik" in response.content.decode()

    def test_home_excludes_pending(self, client, survey_factory):
        survey_factory(status=Survey.Status.PENDING, title="Belum Proses")
        response = client.get("/")
        assert "Belum Proses" not in response.content.decode()


class TestLogin:
    def test_login_page_renders(self, client, db):
        response = client.get(reverse("web:login"))
        assert response.status_code == 200
        assert "Masuk" in response.content.decode()

    def test_login_then_access_upload(self, client, user):
        assert client.login(username="peneliti", password="rahasia123")
        response = client.get(reverse("web:upload"))
        assert response.status_code == 200


class TestUpload:
    def test_upload_requires_login(self, client, db):
        response = client.get(reverse("web:upload"))
        assert response.status_code == 302
        assert reverse("web:login") in response.url

    def test_upload_success_redirects_to_detail(
        self, client, user, valid_metadata
    ):
        client.force_login(user)
        data = dict(valid_metadata)
        data["file"] = SimpleUploadedFile(
            "laporan.pdf", make_pdf_bytes(text=PDF_TEXT), content_type="application/pdf"
        )
        with patch(
            "apps.pipeline.orchestrator.get_llm_client",
            return_value=_MockLLMClient(
                [make_normalization_json(), make_analysis_json()]
            ),
        ):
            response = client.post(reverse("web:upload"), data)
        survey = Survey.objects.get(title=valid_metadata["title"])
        assert response.status_code == 302
        assert response.url == reverse("web:survey_detail", args=[survey.pk])

    def test_upload_failure_renders_error(self, client, user, valid_metadata):
        client.force_login(user)
        data = dict(valid_metadata)
        data["file"] = SimpleUploadedFile(
            "laporan.pdf", make_pdf_bytes(text=PDF_TEXT), content_type="application/pdf"
        )
        with patch(
            "apps.pipeline.orchestrator.get_llm_client",
            return_value=_MockLLMClient(["bukan json"] * 3),
        ):
            response = client.post(reverse("web:upload"), data)
        assert response.status_code == 400
        content = response.content.decode()
        assert "tahap" in content
        assert "normalization" in content

    def test_upload_invalid_form_renders_errors(
        self, client, user, valid_metadata
    ):
        client.force_login(user)
        data = dict(valid_metadata)
        data["title"] = ""
        data["file"] = SimpleUploadedFile(
            "laporan.pdf", make_pdf_bytes(text=PDF_TEXT), content_type="application/pdf"
        )
        response = client.post(reverse("web:upload"), data)
        assert response.status_code == 400


class TestSurveyDetailPage:
    def test_detail_renders_full_card(self, client, completed_survey):
        response = client.get(
            reverse("web:survey_detail", args=[completed_survey.pk])
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Survei Kepuasan Publik" in content
        assert "Kelengkapan disclosure" in content
        assert "Margin of error" in content
        assert "Bukti yang diekstrak" in content
        assert "Ambil data ini" in content
        assert "Bukan penilaian benar/salah" in content
        assert "/api/surveys/" in content

    def test_detail_404_pending(self, client, survey_factory):
        survey = survey_factory(status=Survey.Status.PENDING)
        response = client.get(reverse("web:survey_detail", args=[survey.pk]))
        assert response.status_code == 404

    def test_detail_escapes_content(self, client, survey_factory):
        survey = survey_factory(
            status=Survey.Status.COMPLETED,
            title="<script>alert(1)</script>",
        )
        response = client.get(reverse("web:survey_detail", args=[survey.pk]))
        content = response.content.decode()
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content


class TestStaticPages:
    def test_simulator(self, client, db):
        response = client.get(reverse("web:simulator"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Simulator margin of error" in content

    def test_api_docs(self, client, db):
        response = client.get(reverse("web:api_docs"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "/api/surveys/" in content
        assert "schema_version" in content
