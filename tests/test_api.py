from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.agents.llm import FakeLLMClient
from apps.pipeline.orchestrator import run_pipeline
from apps.surveys.models import Survey
from tests.conftest import (
    EVIDENCE_EXCERPT,
    PAGE_ONE_TEXT,
    PROFILE_EXCERPT,
    make_analysis_json,
    make_normalization_json,
    make_pdf_bytes,
)

PDF_TEXT = PAGE_ONE_TEXT * 2


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="peneliti", password="rahasia123"
    )


def run_fake_pipeline(survey: Survey, responses: list[str]) -> Survey:
    with patch(
        "apps.pipeline.orchestrator.get_llm_client",
        return_value=FakeLLMClient(responses),
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


def upload(api: APIClient, content: bytes, metadata: dict):
    data = dict(metadata)
    data["file"] = SimpleUploadedFile(
        "laporan.pdf", content, content_type="application/pdf"
    )
    return api.post("/api/surveys/", data, format="multipart")


class TestSurveyList:
    def test_anonymous_can_list_completed_public(self, api, completed_survey):
        response = api.get("/api/surveys/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        item = payload["results"][0]
        assert item["title"] == "Survei Kepuasan Publik"
        assert item["disclosure_score"] is not None
        assert item["moe_status"] == "pass"

    def test_non_completed_and_private_excluded(self, api, survey_factory):
        survey_factory(status=Survey.Status.PENDING)
        survey_factory(status=Survey.Status.COMPLETED, is_public=False)
        response = api.get("/api/surveys/")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_pagination_shape(self, api, completed_survey):
        response = api.get("/api/surveys/")
        payload = response.json()
        assert set(payload) == {"count", "next", "previous", "results"}


class TestSurveyDetail:
    def test_detail_payload_stable(self, api, completed_survey):
        response = api.get(f"/api/surveys/{completed_survey.pk}/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "1.0"
        assert set(payload) == {
            "schema_version",
            "survey",
            "profile",
            "evidence",
            "rules",
            "analysis",
            "provenance",
        }
        assert payload["survey"]["id"] == completed_survey.pk
        assert payload["survey"]["file_sha256"] == completed_survey.file_sha256
        assert payload["profile"]["sample_size"]["value"] == 1200
        evidence = payload["evidence"][0]
        assert evidence["value"] == 72.4
        assert evidence["grounded"] is True
        assert evidence["source_page"] == 1
        rule_ids = {rule["rule_id"] for rule in payload["rules"]}
        assert rule_ids == {"R1", "R2"}
        assert payload["analysis"]["summary"]
        provenance = payload["provenance"]
        assert provenance["llm_model"] == "fake-model"
        assert provenance["prompt_version"] == "analysis_v1"
        assert provenance["total_attempts"] == 2

    def test_detail_404_for_pending(self, api, survey_factory):
        survey = survey_factory(status=Survey.Status.PENDING)
        response = api.get(f"/api/surveys/{survey.pk}/")
        assert response.status_code == 404

    def test_detail_404_unknown(self, api, db):
        response = api.get("/api/surveys/999/")
        assert response.status_code == 404


class TestEvidenceCsv:
    def test_csv_rows(self, api, completed_survey):
        response = api.get(f"/api/surveys/{completed_survey.pk}/evidence.csv")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        text = response.content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        assert lines[0].startswith("key,")
        assert len(lines) == 2
        assert "Kepuasan kinerja pemerintah" in lines[1]
        assert "72.4" in lines[1]

    def test_csv_404_for_pending(self, api, survey_factory):
        survey = survey_factory(status=Survey.Status.PENDING)
        response = api.get(f"/api/surveys/{survey.pk}/evidence.csv")
        assert response.status_code == 404


class TestSurveyUpload:
    def test_anonymous_post_forbidden(self, api, valid_metadata, pdf_factory):
        response = upload(api, pdf_factory(), valid_metadata)
        assert response.status_code == 403

    def test_valid_upload_returns_detail(self, api, user, valid_metadata):
        api.force_authenticate(user=user)
        with patch(
            "apps.pipeline.orchestrator.get_llm_client",
            return_value=FakeLLMClient(
                [make_normalization_json(), make_analysis_json()]
            ),
        ):
            response = upload(api, make_pdf_bytes(text=PDF_TEXT), valid_metadata)
        assert response.status_code == 201
        payload = response.json()
        assert payload["schema_version"] == "1.0"
        assert payload["analysis"]["summary"]
        survey = Survey.objects.get(pk=payload["survey"]["id"])
        assert survey.uploaded_by == user

    def test_form_invalid_returns_metadata_stage(self, api, user, valid_metadata):
        api.force_authenticate(user=user)
        metadata = dict(valid_metadata)
        metadata["title"] = ""
        response = upload(api, make_pdf_bytes(text=PDF_TEXT), metadata)
        assert response.status_code == 400
        payload = response.json()
        assert payload["stage"] == "metadata"
        assert "title" in payload["reason"]
        assert payload["attempts"] == 0

    def test_non_pdf_rejected_file_stage(self, api, user, valid_metadata):
        api.force_authenticate(user=user)
        response = upload(api, b"ini bukan pdf", valid_metadata)
        assert response.status_code == 400
        payload = response.json()
        assert payload["stage"] == "file"
        assert payload["reason"]

    def test_llm_failure_returns_stage_and_attempts(
        self, api, user, valid_metadata
    ):
        api.force_authenticate(user=user)
        with patch(
            "apps.pipeline.orchestrator.get_llm_client",
            return_value=FakeLLMClient(["bukan json"] * 3),
        ):
            response = upload(api, make_pdf_bytes(text=PDF_TEXT), valid_metadata)
        assert response.status_code == 400
        payload = response.json()
        assert payload["stage"] == "normalization"
        assert payload["attempts"] == 3
        assert payload["survey_id"]

    def test_idempotent_reupload_returns_200(
        self, api, user, valid_metadata, completed_survey
    ):
        api.force_authenticate(user=user)
        original = completed_survey.file.read()
        completed_survey.file.close()
        response = upload(api, original, valid_metadata)
        assert response.status_code == 200
        assert response.json()["survey"]["id"] == completed_survey.pk
        assert Survey.objects.count() == 1
