"""`manage.py sync_calendar` — enumerate a season and collect every tournament.

Uses the confirmed calendar endpoint (vue-grouped-year-tournaments) to discover
all tournaments in a year — real id, GUID code, dates, and tier — then upserts
each Tournament and (unless --no-matches) collects its matches via day-matches
over the calendar-provided date range. This is the "collect as much as we can"
driver: one command ingests a whole World Tour season.

    python manage.py sync_calendar --year 2026                 # all 2026, with matches
    python manage.py sync_calendar --year 2026 --no-matches    # just the tournament list
    python manage.py sync_calendar --year 2026 --limit 3       # first 3 (testing)
    python manage.py sync_calendar --year 2026 --only 5229,5227 # specific ids
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.normalize import (
    normalize_day_matches,
    upsert_tournament_from_calendar,
)
from apps.ingest.schemas import DayMatches, GroupedYearTournaments

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enumerate a season via the calendar and collect each tournament."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True, help="Season year.")
        parser.add_argument(
            "--no-matches",
            action="store_true",
            help="Only upsert the tournament list; skip day-matches collection.",
        )
        parser.add_argument(
            "--limit", type=int, default=None, help="Process at most N tournaments."
        )
        parser.add_argument(
            "--only",
            default=None,
            help="Comma-separated tournament ids to restrict to.",
        )
        parser.add_argument(
            "--no-cache",
            action="store_true",
            help="Bypass RawCache and re-fetch from the network.",
        )

    def handle(self, *args, **opts):
        with BwfClient(use_cache=not opts["no_cache"]) as client:
            cal = GroupedYearTournaments.model_validate(
                client.get_json(endpoints.vue_grouped_year_tournaments(opts["year"]))
            )
            tours = cal.all_tournaments()
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"{opts['year']}: {len(tours)} tournaments in calendar"
                )
            )

            if opts["only"]:
                wanted = {int(x) for x in opts["only"].split(",") if x.strip()}
                tours = [t for t in tours if t.id in wanted]
            if opts["limit"]:
                tours = tours[: opts["limit"]]

            today = timezone.now().date()
            grand = 0
            for t in tours:
                tournament = upsert_tournament_from_calendar(t)
                line = f"  [{t.id}] {t.name}  ({t.category})  {t.start}..{t.end}"
                if opts["no_matches"] or not t.start or not t.end:
                    self.stdout.write(line + ("" if t.start else "  <no dates>"))
                    continue
                # Tournament tables are always upserted; only fetch matches once
                # the event has actually started (avoids empty future-date pulls).
                if t.start > today:
                    self.stdout.write(line + "  (upcoming — matches skipped)")
                    continue
                n = self._collect_matches(client, tournament, t, today)
                grand += n
                self.stdout.write(line + f"  -> {n} matches")

            if not opts["no_matches"]:
                self.stdout.write(
                    self.style.SUCCESS(f"Total matches ingested: {grand}")
                )

    def _collect_matches(self, client, tournament, cal, today) -> int:
        total = 0
        d = cal.start
        # Don't fetch beyond today for an in-progress event.
        last = min(cal.end, today)
        while d <= last:
            raw = client.get_json(endpoints.day_matches(cal.code, d))
            if isinstance(raw, list) and raw:
                matches = DayMatches.validate_python(raw)
                ingested, _ = normalize_day_matches(matches, tournament=tournament)
                total += ingested
            d = d + timedelta(days=1)
        return total
