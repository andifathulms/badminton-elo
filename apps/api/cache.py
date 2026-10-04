"""Versioned response cache for the public read API.

Every public GET under /api/ is a pure function of the database, and the
database only changes when a command or a staff write bumps the DataVersion.
So a response is cached under (version, path + sorted query) and sent with
`ETag: "<code salt>-<version>"`:

  * a browser that already holds this version gets `304 Not Modified` without
    the view (or the cache) running;
  * any other client gets the stored body without the view running;
  * a bump changes the key prefix, so every old entry is simply never read
    again (they age out of the cache).

Writes bump the version: this middleware bumps after any successful unsafe
request to /api/, and data-writing management commands bump via
apps.ingest.management.base.DataCommand.

Staff/auth/live endpoints are never cached (see NEVER_CACHE).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse, HttpResponseNotModified

from apps.ingest import dataversion

API_PREFIX = "/api/"
NEVER_CACHE = (
    "/api/auth/",
    "/api/refresh",
    "/api/studio/",
    "/api/reconcile/",
)
# Live per-match fetches change without a version bump (see MatchViewSet).
NEVER_CACHE_SUFFIXES = ("/statistics",)
# Unsafe requests to these don't change served data (sessions, job control).
NO_BUMP = ("/api/auth/", "/api/refresh")
CACHE_ALIAS = "api"
CACHE_CONTROL = "no-cache"  # always revalidate; the ETag makes that a cheap 304


def _code_salt() -> str:
    """Fingerprint of the serving code, part of every key, so a deploy never
    serves responses rendered by older code from a shared cache (Redis).
    settings.API_CACHE_SALT (e.g. the image tag) wins; otherwise a hash of the
    source files' sizes and mtimes — the same in every worker of one deploy."""
    if getattr(settings, "API_CACHE_SALT", ""):
        return settings.API_CACHE_SALT
    h = hashlib.sha1()
    root = Path(settings.BASE_DIR)
    for sub in ("apps", "rating", "config"):
        for f in sorted((root / sub).rglob("*.py")):
            st = f.stat()
            h.update(f"{f.relative_to(root)}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:10]


CODE_SALT = _code_salt()


def _cacheable_path(path: str) -> bool:
    return (
        path.startswith(API_PREFIX)
        and not path.startswith(NEVER_CACHE)
        and not path.endswith(NEVER_CACHE_SUFFIXES)
    )


def _key(version: str, request) -> str:
    query = urlencode(sorted(request.GET.lists()), doseq=True)
    raw = f"{request.path}?{query}"
    return f"api:{CODE_SALT}:{version}:{hashlib.sha1(raw.encode()).hexdigest()}"


def _etag(version: str) -> str:
    # Code salt too: after a deploy a browser must not 304 onto old output.
    return f'"{CODE_SALT}-{version}"'


class ApiCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("GET", "HEAD") and _cacheable_path(request.path):
            return self._cached(request)
        response = self.get_response(request)
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and request.path.startswith(API_PREFIX)
            and not request.path.startswith(NO_BUMP)
            and 200 <= response.status_code < 300
        ):
            dataversion.bump()
        return response

    def _cached(self, request):
        dv = dataversion.current()
        if dv is None:
            return self.get_response(request)
        etag = _etag(dv.version)
        if etag in request.headers.get("If-None-Match", ""):
            resp = HttpResponseNotModified()
            resp["ETag"] = etag
            resp["Cache-Control"] = CACHE_CONTROL
            return resp

        cache = caches[CACHE_ALIAS]
        key = _key(dv.version, request)
        hit = cache.get(key)
        if hit is not None:
            content, content_type = hit
            resp = HttpResponse(content, content_type=content_type)
            resp["X-Cache"] = "hit"
        else:
            resp = self.get_response(request)
            if resp.status_code != 200 or getattr(resp, "streaming", False):
                return resp
            if hasattr(resp, "render") and not getattr(resp, "is_rendered", True):
                resp.render()
            cache.set(key, (resp.content, resp.get("Content-Type", "application/json")))
            resp["X-Cache"] = "miss"
        resp["ETag"] = etag
        resp["Cache-Control"] = CACHE_CONTROL
        return resp
