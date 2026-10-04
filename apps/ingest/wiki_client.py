"""Polite, cache-first MediaWiki client for the 1983-2006 gap backfill.

Wikipedia's API is open and CC-BY-SA; we still behave: descriptive UA, on-disk
cache read before any network call, and a rate limit between live requests. One
request fetches a whole article's wikitext (parsed locally by wiki_parse)."""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import httpx

API = "https://en.wikipedia.org/w/api.php"
UA = "badminton-elo-research/1.0 (personal rating project; app.dkb@gmail.com)"
CACHE_DIR = Path("data/wiki_cache")
RECENT_TTL_S = 3 * 24 * 3600  # re-fetch recent-event articles after 3 days
RATE_S = 1.0  # seconds between live requests


class WikiClient:
    def __init__(self, cache_dir: Path | None = None, rate_s: float = RATE_S):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_s = rate_s
        self._last = 0.0
        self._client = httpx.Client(headers={"User-Agent": UA}, timeout=30.0)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _cache_path(self, title: str) -> Path:
        safe = title.replace("/", "_").replace(" ", "_")
        return self.cache_dir / f"{safe}.json"

    def _get(self, params: dict, tries: int = 4) -> dict:
        """GET the API with rate-limit + retry/backoff on transient errors."""
        last = None
        for attempt in range(tries):
            dt = self.rate_s - (time.monotonic() - self._last)
            if dt > 0:
                time.sleep(dt)
            self._last = time.monotonic()
            try:
                r = self._client.get(API, params=params)
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last = e
                time.sleep(2 ** attempt)  # 1, 2, 4, 8s backoff
        raise last

    def _fresh(self, title: str, cp: Path) -> bool:
        """A cached article is reused forever — unless it is about a recent
        event (a year >= last year in the title) and older than RECENT_TTL:
        those pages fill in during and after the event, and a stub cached
        before it (e.g. the 2026 Asian Games in July) must not stick."""
        years = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", title)]
        if not years or max(years) < date.today().year - 1:
            return True
        return time.time() - cp.stat().st_mtime < RECENT_TTL_S

    def wikitext(self, title: str) -> str | None:
        """Full article wikitext, cache-first. None if the page doesn't exist."""
        cp = self._cache_path(title)
        if cp.exists() and self._fresh(title, cp):
            data = json.loads(cp.read_text())
            return data.get("wikitext")

        j = self._get({
            "action": "parse", "page": title, "prop": "wikitext",
            "format": "json", "redirects": 1,
        })
        wt = None
        if "parse" in j:
            wt = j["parse"].get("wikitext", {}).get("*")
        # cache both hits and misses (miss -> wikitext None) so we don't refetch
        cp.write_text(json.dumps({"title": title, "wikitext": wt}))
        return wt

    def category_members(self, category: str) -> list[str]:
        """All page titles in Category:<category> (cache-first, paginated)."""
        cp = self._cache_path("CAT_" + category)
        if cp.exists():
            return json.loads(cp.read_text()).get("members", [])
        members: list[str] = []
        cont = None
        while True:
            params = {
                "action": "query", "list": "categorymembers",
                "cmtitle": f"Category:{category}", "cmlimit": 500, "format": "json",
            }
            if cont:
                params["cmcontinue"] = cont
            j = self._get(params)
            members += [m["title"] for m in j.get("query", {}).get("categorymembers", [])]
            cont = j.get("continue", {}).get("cmcontinue")
            if not cont:
                break
        cp.write_text(json.dumps({"category": category, "members": members}))
        return members
