import os
from pathlib import Path

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
_env_path = (BASE_DIR / ".env").resolve()
load_dotenv(dotenv_path=_env_path, override=True)
_env_vars = dotenv_values(_env_path) if _env_path.exists() else {}
if not _env_vars and (Path.cwd() / ".env").exists():
    _env_vars = dotenv_values(Path.cwd() / ".env") or {}


def _env(key: str, fallback: str) -> str:
    return _env_vars.get(key) or os.getenv(key, fallback)


DEBUG = _env("DEBUG", "True").lower() in ("true", "1", "yes")

_secret_key = _env("DJANGO_SECRET_KEY", "")
if not _secret_key:
    if DEBUG:
        _secret_key = "dev-only-secret-key-change-me-to-at-least-32-characters"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY environment variable is not set. Required in production."
        )
SECRET_KEY = _secret_key

_allowed_hosts_raw = _env("DJANGO_ALLOWED_HOSTS", "")
if not _allowed_hosts_raw:
    if DEBUG:
        ALLOWED_HOSTS = ["*"]
    else:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS environment variable is not set. Required in production."
        )
else:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_raw.split(",") if h.strip()]

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = _env("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = _env("TWILIO_AUTH_TOKEN", "")

# ── Sentry ────────────────────────────────────────────────────────────────────
SENTRY_DSN = _env("SENTRY_DSN", "")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=_env("DJANGO_ENV", "production"),
        traces_sample_rate=0.2,
        send_default_pii=False,
    )

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    "rest_framework",
    # Project apps
    "core",
    "businesses",
    "queues",
    "notifications",
    "customer",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("DB_NAME", "queuelight"),
        "USER": _env("DB_USER", "postgres"),
        "PASSWORD": _env("DB_PASSWORD", "postgres"),
        "HOST": _env("DB_HOST", "127.0.0.1"),
        "PORT": _env("DB_PORT", "5432"),
    }
}

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "1000/hour",
        "queue_join": "20/hour",
        "staff_login": "10/minute",
    },
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in _env("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = DEBUG

# ── Unfold admin ──────────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "Queue Light",
    "SITE_HEADER": "Queue Light Admin",
    "SITE_SYMBOL": "queue",
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = _env("DJANGO_TIME_ZONE", "America/Toronto")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}

# Media files (QR code PNGs if stored to disk)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/staff/login/"
