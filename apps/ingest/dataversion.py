"""The served-data version: bump on every write, read on every request.

`bump()` is called by every data-writing management command (via
apps.ingest.management.base.DataCommand), by the refresh pipeline, and after
any successful write request (Studio, reconcile). `current()` is one primary-key
lookup.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.db import DatabaseError
from django.db.models import Count, Max
from django.utils import timezone

from .boards import ACTIVE_DAYS


def _new_version() -> str:
    return f"{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"


def refresh_match_counts() -> int:
    """Recompute Tournament.match_count for every tournament whose count
    changed (one GROUP BY + a bulk update of the few that moved)."""
    from .models import Match, Tournament

    counts = dict(
        Match.objects.order_by().values_list("tournament_id").annotate(n=Count("match_id"))
    )
    stale = [
        t for t in Tournament.objects.only("tournament_id", "match_count")
        if t.match_count != counts.get(t.tournament_id, 0)
    ]
    for t in stale:
        t.match_count = counts.get(t.tournament_id, 0)
    Tournament.objects.bulk_update(stale, ["match_count"], batch_size=1000)
    return len(stale)


def bump():
    """Refresh derived serving metadata (tournament match counts, the active
    cutoff) and stamp a new version. Returns the row."""
    from .models import DataVersion, PlayerRating

    refresh_match_counts()
    latest = PlayerRating.objects.aggregate(m=Max("last_match_utc"))["m"]
    row, _ = DataVersion.objects.update_or_create(
        pk=1,
        defaults={
            "version": _new_version(),
            "updated_utc": timezone.now(),
            "latest_match_utc": latest,
            "active_cutoff": (latest - timedelta(days=ACTIVE_DAYS)) if latest else None,
        },
    )
    return row


def current():
    """The DataVersion row, creating it on first use. None if the table is
    missing (e.g. before migrate) — callers then skip caching."""
    from .models import DataVersion

    try:
        row = DataVersion.objects.filter(pk=1).first()
        return row or bump()
    except DatabaseError:
        return None
