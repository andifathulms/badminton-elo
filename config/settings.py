"""Django settings for the badminton rating system.

Phase 1 = SQLite + no Docker (get the first ingested result before containers).
Postgres/Docker arrives in Phase 3 by swapping DATABASES only.

Rating-engine constants (PRD §8) live here and are passed *into* the pure
`rating/` package by `manage.py rate` — the engine never reads settings itself.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# --- Core -------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-insecure-key-change-me-in-production"
)
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local
    "apps.ingest",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# Phase 1: SQLite under data/ (gitignored). Phase 3: swap to Postgres via env.
if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    # data/ is gitignored; create it so SQLite can open the file on first run.
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data" / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / tz --------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static -----------------------------------------------------------------
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Ingestion config (PRD §8) — read by apps/ingest.
# ---------------------------------------------------------------------------
# Tournament GUIDs to collect with `scrape_days --all`. Env override (comma-
# separated) wins; otherwise fall back to the known-good defaults below.
# Each entry is verified to return data from the day-matches endpoint.
_DEFAULT_TOURNAMENT_CODES = [
    "71AC3AB2-C072-444C-B479-4AC73C756C14",  # PERODUA Malaysia Masters 2026 (180 matches)
]
TOURNAMENT_CODES = [
    c for c in os.environ.get("TOURNAMENT_CODES", "").split(",") if c
] or _DEFAULT_TOURNAMENT_CODES

INCLUDE_QUALIFYING = _env_bool("INCLUDE_QUALIFYING", False)
RATE_LIMIT_QPS = float(os.environ.get("RATE_LIMIT_QPS", "1"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "20"))
HTTP_MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", "3"))
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "badminton-elo/0.1 (research; contact: officialandifathul@gmail.com)",
)
# Where cached raw JSON responses are written alongside RawCache rows.
RAW_CACHE_DIR = BASE_DIR / "data" / "raw"

# ---------------------------------------------------------------------------
# Rating-engine constants (PRD §7–§8). Passed INTO rating/ by `manage.py rate`;
# the pure engine never imports Django or reads these directly.
# ---------------------------------------------------------------------------
RATING = {
    "MU_INIT": 1500.0,
    "RD_INIT": 350.0,
    "SIGMA_INIT": 0.06,
    "TAU": 0.5,
    "PAIR_BLEND": "mean",
    "LAMBDA": 0.5,
    "M_MIN": 0.7,
    "M_MAX": 1.4,
    "D_FLOOR": 0.50,
    "K_RETIRE": 0.3,
    "RD_INFLATE_C": 34.6,
    "TIER_WEIGHTS": {
        "Super1000": 1.1,
        "Super750": 1.05,
        "Super500": 1.0,
        "Super300": 0.95,
        "Super100": 0.9,
    },
}
