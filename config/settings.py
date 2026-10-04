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
    # Third-party (Phase 3 serving)
    "rest_framework",
    "corsheaders",
    # Local
    "apps.ingest",
    "apps.api",
]

MIDDLEWARE = [
    # First, so it compresses last: JSON shrinks 5-8x (a 197 KB rating history
    # goes out as ~30 KB). Only applied when the client sends Accept-Encoding.
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last: serves public GET /api/* from a cache keyed on the DataVersion and
    # answers 304 when the browser already has it (apps/api/cache.py).
    "apps.api.cache.ApiCacheMiddleware",
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
    # SQLITE_PATH lets a read-only server (e.g. Docker) point at a snapshot
    # while a scrape keeps writing the primary db.sqlite3.
    _sqlite_name = os.environ.get("SQLITE_PATH") or (BASE_DIR / "data" / "db.sqlite3")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_name,
            "OPTIONS": {
                # WAL: readers never block on a writer (a rebuild runs while the
                # site serves) and see a consistent snapshot. NORMAL is safe
                # under WAL. mmap + a 64 MB page cache keep hot tables in memory.
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA synchronous=NORMAL;"
                    "PRAGMA mmap_size=1073741824;"
                    "PRAGMA cache_size=-65536;"
                    "PRAGMA temp_store=MEMORY;"
                ),
                "timeout": 30,  # seconds to wait on a locked database
                "transaction_mode": "IMMEDIATE",  # no mid-transaction lock upgrades
            },
        }
    }

# Reuse connections across requests (with a liveness check) instead of
# reconnecting — and re-running the PRAGMAs above — on every request.
DATABASES["default"]["CONN_MAX_AGE"] = int(os.environ.get("DB_CONN_MAX_AGE", "60"))
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

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

# --- Caches -----------------------------------------------------------------
# "api" holds rendered API responses keyed by DataVersion (apps/api/cache.py).
# In-process memory by default (bounded); set REDIS_URL to share one cache
# across gunicorn workers / containers.
if os.environ.get("REDIS_URL"):
    _api_cache = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
        "TIMEOUT": 7 * 24 * 3600,
    }
else:
    _api_cache = {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-responses",
        "TIMEOUT": 7 * 24 * 3600,
        "OPTIONS": {"MAX_ENTRIES": 3000},
    }
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "api": _api_cache,
}
# Part of every API cache key; set it per deploy (e.g. the image tag) when the
# cache is shared. Empty = derive from the source files (apps/api/cache.py).
API_CACHE_SALT = os.environ.get("API_CACHE_SALT", "")

# --- DRF (Phase 3 read API) -------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Read-only public API for the MVP.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}

# --- CORS (React dev server) ------------------------------------------------
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8010,http://127.0.0.1:8010",
).split(",")

# Origins allowed to POST (Studio actions come from the frontend origin, which is
# a different port than the API, so Django's CSRF Origin check needs it listed).
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:8010,http://127.0.0.1:8010,"
        "http://localhost:8011,http://127.0.0.1:8011,"
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if o
]

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
    # Margin (PRD §7.3): M = 1 + LAMBDA·(2d − 1), clamped to [M_MIN, M_MAX].
    # D_FLOOR = 0 lets a narrow win count for LESS than a plain win (M < 1), not
    # only blowouts for more. Tuned with `manage.py backtest`: logloss 0.5350 ->
    # 0.5250 on 2023+, confirmed 0.5340 -> 0.5240 on unseen 2016-2019.
    "LAMBDA": 2.0,
    "M_MIN": 0.4,
    "M_MAX": 2.5,
    "D_FLOOR": 0.0,
    "K_RETIRE": 0.3,
    "RD_INFLATE_C": 34.6,
    # Rank-based seeding (PRD §7.6): rank 1 -> SEED_RANK_TOP_MU, rank
    # SEED_RANK_BASE+ -> MU_INIT, with a high SEED_RD (prior, not truth).
    "SEED_RANK_TOP_MU": 2300.0,
    "SEED_RANK_BASE": 400,
    "SEED_RD": 300.0,
    # Cross-discipline prior (PRD §7.6): a player's first match in a new
    # discipline starts from 70% of their edge elsewhere, rd 200 — instead of
    # 1500 ± 350 as if they'd never played. Backtest: 0.5250 -> 0.5209 (2023+),
    # 0.5240 -> 0.5204 (unseen 2016-2019).
    "CROSS_PRIOR_WEIGHT": 0.7,
    "CROSS_PRIOR_RD": 200.0,
    "CROSS_PRIOR_MIN_MATCHES": 5,
    # All-time peak counts only once a rating is settled (rd <= this), so an
    # early lucky streak at rd 200+ can't post a peak. See rating/peaks.py.
    "PEAK_MAX_RD": 100.0,
    # Incremental `rate` keeps an undo log for periods starting within this
    # many days of the newest one, so changes there (an ongoing tournament
    # gaining matches) replay just the tail; older changes rebuild fully.
    "UNDO_DAYS": 120,
    # W_tier per prestige grade (rate.TIER_GRADES: major/high/mid/low). Empty =
    # every match weighs 1.0. Backtested graded weights (e.g. major 1.1 ... low
    # 0.9) were no better than none (logloss 0.5218 vs 0.5210), so it's off.
    "TIER_WEIGHTS": {},
}
