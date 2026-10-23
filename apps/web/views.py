from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.pipeline.orchestrator import run_pipeline
from apps.surveys.forms import SurveyUploadForm
from apps.surveys.messages import friendly_status_message
from apps.surveys.models import Survey
from apps.surveys.services import create_or_get_survey

DISCLAIMER = "Alat bantu literasi bukti. Bukan penilaian benar/salah atas survei."


def _completed_public_queryset():
    return Survey.objects.filter(
        status=Survey.Status.COMPLETED, is_public=True
    ).prefetch_related("rule_results")


def _rule_map(survey: Survey) -> dict[str, Survey.rule_results.rel.related_model]:
    return {rule.rule_id: rule for rule in survey.rule_results.all()}


class HomeView(TemplateView):
    template_name = "web/home.html"

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        surveys = []
        for survey in _completed_public_queryset().order_by("-publication_date"):
            rules = _rule_map(survey)
            r2 = rules.get("R2")
            r1 = rules.get("R1")
            surveys.append(
                {
                    "survey": survey,
                    "disclosure_score": r2.details.get("score") if r2 else None,
                    "disclosure_total": r2.details.get("total") if r2 else None,
                    "moe_status": r1.status if r1 else None,
                }
            )
        context["surveys"] = surveys
        context["disclaimer"] = DISCLAIMER
        return context


class UploadView(LoginRequiredMixin, View):
    template_name = "web/upload.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(
            request,
            self.template_name,
            {"form": SurveyUploadForm(), "disclaimer": DISCLAIMER},
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SurveyUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "disclaimer": DISCLAIMER},
                status=400,
            )
        survey, _created = create_or_get_survey(
            cleaned_data=form.cleaned_data,
            uploaded_file=form.cleaned_data["file"],
            user=request.user,
        )
        if survey.status == Survey.Status.PENDING:
            survey = run_pipeline(survey.pk)
        if survey.status == Survey.Status.COMPLETED:
            messages.success(request, "Survei berhasil dianalisis.")
            return redirect("web:survey_detail", pk=survey.pk)
        messages.error(
            request,
            f"Analisis berhenti di tahap {survey.error_stage or survey.status}. "
            f"{friendly_status_message(survey.status)} "
            f"Detail: {survey.error_reason}",
        )
        return render(
            request,
            self.template_name,
            {"form": SurveyUploadForm(), "disclaimer": DISCLAIMER},
            status=400,
        )


class SurveyDetailView(View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        survey = get_object_or_404(_completed_public_queryset(), pk=pk)
        rules = _rule_map(survey)
        r1 = rules.get("R1")
        r2 = rules.get("R2")
        analysis = getattr(survey, "analysis", None)
        profile = getattr(survey, "profile", None)
        json_url = request.build_absolute_uri(
            reverse("api:survey-detail", args=[survey.pk])
        )
        csv_url = request.build_absolute_uri(
            reverse("api:survey-evidence-csv", args=[survey.pk])
        )
        context = {
            "survey": survey,
            "profile": profile,
            "evidence": survey.evidence.order_by("key"),
            "r1": r1,
            "r2": r2,
            "moe": r1.details if r1 else None,
            "disclosure_items": r2.details.get("items", []) if r2 else None,
            "disclosure_score": r2.details.get("score") if r2 else None,
            "disclosure_total": r2.details.get("total") if r2 else None,
            "analysis": analysis,
            "json_url": json_url,
            "csv_url": csv_url,
            "disclaimer": DISCLAIMER,
        }
        return render(request, "web/detail.html", context)


class SimulatorView(TemplateView):
    template_name = "web/simulator.html"


class ApiDocsView(TemplateView):
    template_name = "web/api_docs.html"


upload = UploadView.as_view()
survey_detail = SurveyDetailView.as_view()
home = HomeView.as_view()
simulator = SimulatorView.as_view()
api_docs = ApiDocsView.as_view()
