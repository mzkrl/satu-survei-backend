from django.contrib.auth import views as auth_views
from django.urls import path

from apps.web import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("upload/", views.upload, name="upload"),
    path("surveys/<int:pk>/", views.survey_detail, name="survey_detail"),
    path("simulator/", views.simulator, name="simulator"),
    path("api-docs/", views.api_docs, name="api_docs"),
    path("masuk/", auth_views.LoginView.as_view(template_name="web/login.html"), name="login"),
    path(
        "keluar/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]
