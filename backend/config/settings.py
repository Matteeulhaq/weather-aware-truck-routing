"""
Django settings for the Weather-Aware Truck Routing app.

Environment-driven configuration: local values live in backend/.env (gitignored);
on Render they come from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env when present (local development).
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", "django-insecure-dev-only-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Third-party API keys (server-side only — never exposed to the client).
ORS_API_KEY = env("ORS_API_KEY")

# Application definition

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise first in line after security: serves the built SPA
    # (hashed + pre-compressed assets) from the same process.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    # GZip compresses the (large) JSON plan responses.
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# The app is stateless — sqlite exists only as Django's default and is unused.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files: the built React app (client/dist) is served by Django.
# The Vite build sets base='/static/' so asset URLs match STATIC_URL.

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

STATIC_URL = "static/"

STATICFILES_DIRS = [BASE_DIR.parent / "client" / "dist"]

STATIC_ROOT = BASE_DIR / "staticfiles"


# DRF — JSON-only, public API. No auth: the app has no user accounts, which
# keeps Django's auth/contenttypes machinery out of INSTALLED_APPS.
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# In-process cache: weather 15 min, directions 60 min, geocode 24 h.
# Single gunicorn worker makes per-process caching safe.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "routing-cache",
    }
}

# Logging: WARNING+ from our services lands in Render's log stream.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "routing": {"handlers": ["console"], "level": "INFO"},
    },
}
