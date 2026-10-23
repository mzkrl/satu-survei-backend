from django.conf import settings


def test_settings_loaded() -> None:
    assert settings.SECRET_KEY
    assert settings.DEBUG in (True, False)


def test_apps_registered() -> None:
    for app in ("apps.surveys", "apps.pipeline", "apps.agents", "apps.rules", "apps.api", "apps.web"):
        assert app in settings.INSTALLED_APPS
