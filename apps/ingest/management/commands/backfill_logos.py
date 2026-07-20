"""Backfill Tournament.logo_url from cached BWF calendar payloads.

The vue-grouped-year-tournaments payload carries each tournament's `logo`
(and `cat_logo`) keyed by its GUID `code`, which matches Tournament.code.
Cache-only — no network."""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ingest.models import RawCache, Tournament


def _walk(obj, out):
    """Collect {code: logo} for every tournament-like dict in the payload."""
    if isinstance(obj, dict):
        code, logo = obj.get("code"), obj.get("logo")
        if code and logo:
            out[code] = logo
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)


class Command(BaseCommand):
    help = "Fill Tournament.logo_url from cached calendar payloads."

    def handle(self, *args, **opts):
        code_logo: dict[str, str] = {}
        for r in RawCache.objects.filter(url__contains="vue-grouped-year"):
            try:
                body = json.loads(r.body) if isinstance(r.body, str) else r.body
            except Exception:
                continue
            _walk(body, code_logo)
        self.stdout.write(f"found logos for {len(code_logo)} tournament codes")

        updated = 0
        batch = []
        for t in Tournament.objects.exclude(code=None).filter(logo_url=""):
            logo = code_logo.get(t.code)
            if logo:
                t.logo_url = logo[:512]
                batch.append(t)
            if len(batch) >= 500:
                Tournament.objects.bulk_update(batch, ["logo_url"]); updated += len(batch); batch = []
        if batch:
            Tournament.objects.bulk_update(batch, ["logo_url"]); updated += len(batch)
        self.stdout.write(self.style.SUCCESS(f"Set logo_url on {updated} tournaments."))
