"""Polite, cache-first MediaWiki client for the 1983-2006 gap backfill.

Wikipedia's API is open and CC-BY-SA; we still behave: descriptive UA, on-disk
cache read before any network call, and a rate limit between live requests. One
request fetches a whole article's wikitext (parsed locally by wiki_parse)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

API = "https://en.wikipedia.org/w/api.php"
UA = "badminton-elo-research/1.0 (personal rating project; app.dkb@gmail.com)"
CACHE_DIR = Path("data/wiki_cache")
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

    def wikitext(self, title: str) -> str | None:
        """Full article wikitext, cache-first. None if the page doesn't exist."""
        cp = self._cache_path(title)
        if cp.exists():
            data = json.loads(cp.read_text())
            return data.get("wikitext")

        dt = self.rate_s - (time.monotonic() - self._last)
        if dt > 0:
            time.sleep(dt)
        self._last = time.monotonic()

        r = self._client.get(API, params={
            "action": "parse", "page": title, "prop": "wikitext",
            "format": "json", "redirects": 1,
        })
        r.raise_for_status()
        j = r.json()
        wt = None
        if "parse" in j:
            wt = j["parse"].get("wikitext", {}).get("*")
        # cache both hits and misses (miss -> wikitext None) so we don't refetch
        cp.write_text(json.dumps({"title": title, "wikitext": wt}))
        return wt
