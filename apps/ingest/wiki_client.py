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
    """`lang` picks the Wikipedia edition (default English). Non-English
    editions cache under data/wiki_cache/<lang>/."""

    def __init__(self, cache_dir: Path | None = None, rate_s: float = RATE_S,
                 lang: str = "en"):
        self.lang = lang
        self.api = API if lang == "en" else f"https://{lang}.wikipedia.org/w/api.php"
        self.cache_dir = cache_dir or (CACHE_DIR if lang == "en" else CACHE_DIR / lang)
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
                r = self._client.get(self.api, params=params)
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

    def langlinks(self, titles: list[str], to: str = "en") -> dict[str, str | None]:
        """{title: the linked article title in edition `to`, or None}, batched
        50 titles per request (redirects followed) and cached per title."""
        cp = self.cache_dir / f"_langlinks_{to}.json"
        known: dict = json.loads(cp.read_text()) if cp.exists() else {}
        todo = [t for t in dict.fromkeys(titles) if t not in known]
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            j = self._get({"action": "query", "titles": "|".join(batch), "prop": "langlinks",
                           "lllang": to, "lllimit": 500, "redirects": 1, "format": "json"})
            q = j.get("query", {})
            alias = {}
            for key in ("normalized", "redirects"):
                for r in q.get(key, []):
                    alias[r["to"]] = alias.get(r["from"], r["from"])
            for page in q.get("pages", {}).values():
                links = page.get("langlinks") or []
                target = links[0]["*"] if links else None
                src = page.get("title")
                # map back through redirects/normalisation to what we asked for
                origin = src
                while origin in alias:
                    origin = alias[origin]
                for t in (src, origin):
                    if t in batch:
                        known[t] = target
            for t in batch:
                known.setdefault(t, None)
            cp.write_text(json.dumps(known))
        return {t: known.get(t) for t in titles}

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
                "cmtitle": category if ":" in category else f"Category:{category}",
                "cmlimit": 500, "format": "json",
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
