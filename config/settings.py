from pathlib import Path
import os

import dj_database_url

from config.env import env_bool, env_float, env_int, env_str, load_env

load_env()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env_str("SECRET_KEY", "insecure-dev-secret-key-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env_str("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.surveys",
    "apps.pipeline",
    "apps.agents",
    "apps.rules",
    "apps.api",
    "apps.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db_url = env_str("DATABASE_URL") or f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"
DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=600)}
if _db_url.startswith("sqlite:///"):
    _db_name = DATABASES["default"].get("NAME")
    if _db_name and not Path(str(_db_name)).is_absolute():
        DATABASES["default"]["NAME"] = str(BASE_DIR / str(_db_name))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "web:login"
LOGIN_REDIRECT_URL = "web:upload"
LOGOUT_REDIRECT_URL = "web:home"

LANGUAGE_CODE = "id-id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "whitenoise.storage.CompressedStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

THROTTLE_UPLOAD_RATE = env_str("THROTTLE_UPLOAD_RATE", "10/min")

REDIS_URL = env_str("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "satusurvey",
        }
    }

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", True)

LLM_PROVIDER = env_str("LLM_PROVIDER", "fake")
ANTHROPIC_API_KEY = env_str("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = env_str("ANTHROPIC_BASE_URL", "")
LLM_MODEL = env_str("LLM_MODEL", "")
LLM_TIMEOUT_S = env_int("LLM_TIMEOUT_S", 90)
PIPELINE_MAX_RETRIES = env_int("PIPELINE_MAX_RETRIES", 2)

MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 15)
MAX_PAGES = env_int("MAX_PAGES", 60)
MAX_TEXT_CHARS = env_int("MAX_TEXT_CHARS", 150000)
MIN_CHARS_PER_PAGE = env_int("MIN_CHARS_PER_PAGE", 200)
GROUNDING_MIN_RATIO = env_float("GROUNDING_MIN_RATIO", 0.6)
DEMO_MODE = env_bool("DEMO_MODE", False)
DEMO_CACHE_DIR = BASE_DIR / "demo" / "cached"

PIPELINE_TOTAL_BUDGET_S = env_int("PIPELINE_TOTAL_BUDGET_S", 240)
