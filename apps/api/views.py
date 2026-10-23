from __future__ import annotations

import csv
import io

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, views
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from apps.api.serializers import SurveyListSerializer, build_detail_payload
from apps.pipeline.orchestrator import run_pipeline
from apps.surveys.forms import SurveyUploadForm
from apps.surveys.models import Survey
from apps.surveys.services import create_or_get_survey

CSV_COLUMNS = [
    "key",
    "label_original",
    "label_normalized",
    "value",
    "value_raw",
    "unit",
    "period",
    "geography",
    "definition",
    "source_page",
    "source_excerpt",
    "unknown_fields",
    "grounded",
]


def _completed_public_queryset():
    return Survey.objects.filter(
        status=Survey.Status.COMPLETED, is_public=True
    ).prefetch_related("rule_results")


def _form_errors(form: SurveyUploadForm) -> dict[str, list[str]]:
    return {
        field: [str(message) for message in messages]
        for field, messages in form.errors.items()
    }


class SurveyListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = SurveyListSerializer

    def get_queryset(self):
        return _completed_public_queryset()

    def create(self, request, *args, **kwargs):
        form = SurveyUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return Response(
                {"stage": "metadata", "reason": _form_errors(form), "attempts": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )
        survey, created = create_or_get_survey(
            cleaned_data=form.cleaned_data,
            uploaded_file=form.cleaned_data["file"],
            user=request.user,
        )
        if survey.status == Survey.Status.PENDING:
            survey = run_pipeline(survey.pk)
        if survey.status != Survey.Status.COMPLETED:
            return Response(
                {
                    "survey_id": survey.pk,
                    "stage": survey.error_stage or survey.status,
                    "reason": survey.error_reason,
                    "attempts": survey.attempts.count(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            build_detail_payload(survey),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SurveyDetailView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk: int):
        survey = get_object_or_404(_completed_public_queryset(), pk=pk)
        return Response(build_detail_payload(survey))


class SurveyEvidenceCsvView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk: int):
        survey = get_object_or_404(_completed_public_queryset(), pk=pk)
        buffer = io.StringIO()
        buffer.write("\ufeff")
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        for record in survey.evidence.order_by("key"):
            writer.writerow(
                [
                    record.key,
                    record.label_original,
                    record.label_normalized,
                    record.value,
                    record.value_raw,
                    record.unit,
                    record.period,
                    record.geography,
                    record.definition,
                    record.source_page,
                    record.source_excerpt,
                    ";".join(record.unknown_fields),
                    record.grounded,
                ]
            )
        response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="survei-{survey.pk}-bukti.csv"'
        )
        return response
