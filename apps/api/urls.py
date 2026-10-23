from django.urls import path

from apps.api import views

app_name = "api"

urlpatterns = [
    path("surveys/", views.SurveyListCreateView.as_view(), name="survey-list"),
    path("surveys/<int:pk>/", views.SurveyDetailView.as_view(), name="survey-detail"),
    path(
        "surveys/<int:pk>/evidence.csv",
        views.SurveyEvidenceCsvView.as_view(),
        name="survey-evidence-csv",
    ),
]
