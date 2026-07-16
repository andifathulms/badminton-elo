"""`manage.py ingest_status` — row counts, last fetch, cache size (PRD §10).

A quick health read on what has been ingested so far. Read-only.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.ingest.models import (
    Draw,
    Game,
    Match,
    MatchPlayer,
    Player,
    RawCache,
    Tournament,
)


class Command(BaseCommand):
    help = "Show ingested row counts, per-event match totals, and cache state."

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING("Ingestion status"))

        counts = [
            ("Tournaments", Tournament.objects.count()),
            ("Draws", Draw.objects.count()),
            ("Players", Player.objects.count()),
            ("Matches", Match.objects.count()),
            ("  rating-excluded", Match.objects.filter(rating_excluded=True).count()),
            ("MatchPlayers", MatchPlayer.objects.count()),
            ("Games", Game.objects.count()),
            ("RawCache entries", RawCache.objects.count()),
        ]
        for label, n in counts:
            self.stdout.write(f"  {label:<20} {n:>8}")

        # Per-event breakdown.
        by_event = (
            Match.objects.values("event")
            .annotate(n=Count("match_id"))
            .order_by("-n")
        )
        if by_event:
            self.stdout.write(self.style.MIGRATE_HEADING("Matches by event"))
            for row in by_event:
                self.stdout.write(f"  {row['event'] or '?':<6} {row['n']:>6}")

        last = RawCache.objects.order_by("-fetched_utc").first()
        if last:
            self.stdout.write(
                self.style.MIGRATE_HEADING("Cache")
                + f"\n  last fetch: {last.fetched_utc:%Y-%m-%d %H:%M:%S UTC}"
            )
