"""Polite BWF fan-API client (PRD §4, domain rule 9).

Responsibilities, all enforced here so the scraper stays simple:
  * read-through cache — a matching RawCache row means ZERO network I/O
  * rate limit — at most RATE_LIMIT_QPS requests/second (default 1)
  * retry with exponential backoff on transient errors
  * descriptive User-Agent; configurable timeout
  * mirror every raw body to data/raw/ for offline inspection

This is the only place in the codebase allowed to make outbound HTTP requests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.utils import timezone

from . import endpoints
from ..models import RawCache

logger = logging.getLogger(__name__)

# Transient statuses worth retrying (rate-limit + upstream hiccups).
_RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class Response:
    """Minimal fetch result: the parsed JSON plus provenance."""

    url: str
    status: int
    body: str
    from_cache: bool

    def json(self):
        return json.loads(self.body)


class BwfClient:
    """Rate-limited, cached HTTP client for the BWF fan API.

    Use as a context manager so the underlying httpx client is closed:
        with BwfClient() as client:
            data = client.get_json(endpoints.vue_tournament_draws(code))
    """

    def __init__(
        self,
        *,
        qps: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        user_agent: str | None = None,
        use_cache: bool = True,
    ):
        self.min_interval = 1.0 / (qps or settings.RATE_LIMIT_QPS)
        self.timeout = timeout if timeout is not None else settings.HTTP_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else settings.HTTP_MAX_RETRIES
        )
        self.user_agent = user_agent or settings.USER_AGENT
        self.use_cache = use_cache
        self._last_request_ts = 0.0
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                # The vue-* endpoints 404/500 without the fan-site Origin/Referer;
                # day-matches is unaffected. See endpoints.REQUEST_ORIGIN.
                "Origin": endpoints.REQUEST_ORIGIN,
                "Referer": endpoints.REQUEST_REFERER,
            },
            follow_redirects=True,
        )

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "BwfClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- public API ---------------------------------------------------------
    def get_json(self, url: str):
        """Fetch a URL and return parsed JSON (cache-first)."""
        return self.fetch(url).json()

    def fetch(self, url: str) -> Response:
        """Return a Response for ``url``, reading RawCache before the network."""
        if self.use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                logger.debug("cache hit %s", url)
                return cached
        resp = self._fetch_network(url)
        self._write_cache(resp)
        return resp

    # -- cache --------------------------------------------------------------
    def _read_cache(self, url: str) -> Response | None:
        try:
            row = RawCache.objects.get(pk=url)
        except RawCache.DoesNotExist:
            return None
        return Response(url=url, status=row.status, body=row.body, from_cache=True)

    def _write_cache(self, resp: Response) -> None:
        RawCache.objects.update_or_create(
            url=resp.url,
            defaults={
                "fetched_utc": timezone.now(),
                "status": resp.status,
                "body": resp.body,
            },
        )
        self._mirror_to_disk(resp)

    def _mirror_to_disk(self, resp: Response) -> None:
        """Best-effort mirror to data/raw/ — never fatal to a scrape."""
        try:
            raw_dir = settings.RAW_CACHE_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha1(resp.url.encode()).hexdigest()[:16]
            stem = (urlparse(resp.url).path.rsplit("/", 1)[-1] or "root")[:60]
            (raw_dir / f"{stem}.{digest}.json").write_text(resp.body)
        except OSError as exc:  # pragma: no cover - disk mirror is optional
            logger.warning("could not mirror %s to disk: %s", resp.url, exc)

    # -- network ------------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    def _fetch_network(self, url: str) -> Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                r = self._client.get(url)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._backoff(attempt, f"transport error: {exc}")
                continue

            if r.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                self._backoff(attempt, f"status {r.status_code}")
                continue

            r.raise_for_status()
            logger.info("fetched %s -> %s", url, r.status_code)
            return Response(
                url=url, status=r.status_code, body=r.text, from_cache=False
            )

        raise httpx.HTTPError(
            f"exhausted {self.max_retries} retries for {url}: {last_exc}"
        )

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = min(2 ** (attempt - 1), 30)
        logger.warning("retry %d (%s); backing off %.1fs", attempt, reason, delay)
        time.sleep(delay)
