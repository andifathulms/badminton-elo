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

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.normalize import (
    normalize_day_matches,
    upsert_tournament_from_calendar,
)
from apps.ingest.schemas import DayMatches, GroupedYearTournaments

logger = logging.getLogger(__name__)


def _is_senior(category: str) -> bool:
    """A senior event = anything that isn't Junior or Para-Badminton."""
    label = (category or "").lower()
    return "junior" not in label and "para" not in label


class Command(BaseCommand):
    help = "Enumerate a season via the calendar and collect each tournament."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="A single season year.")
        parser.add_argument("--start-year", type=int, help="First year of a range.")
        parser.add_argument("--end-year", type=int, help="Last year of a range.")
        parser.add_argument(
            "--tiers",
            choices=("worldtour", "senior", "all"),
            default="worldtour",
            help="worldtour = Super 300-1000; senior = every tier except Junior/"
            "Para; all = everything. (senior/all query the full id space.)",
        )
        parser.add_argument(
            "--no-matches",
            action="store_true",
            help="Only upsert the tournament list; skip day-matches collection.",
        )
        parser.add_argument(
            "--skip-collected",
            action="store_true",
            help="Skip tournaments that already have matches (resumable bulk pull).",
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
        years = self._years(opts)
        categories = (
            endpoints.CALENDAR_CATEGORIES
            if opts["tiers"] == "worldtour"
            else endpoints.ALL_CATEGORIES
        )
        with BwfClient(use_cache=not opts["no_cache"]) as client:
            grand_t = grand_m = 0
            for year in years:
                nt, nm = self._sync_year(client, year, categories, opts)
                grand_t += nt
                grand_m += nm
            if len(years) > 1:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"All years: {grand_t} tournaments"
                        + ("" if opts["no_matches"] else f", {grand_m} matches")
                    )
                )

    def _years(self, opts) -> list[int]:
        if opts["start_year"] and opts["end_year"]:
            return list(range(opts["start_year"], opts["end_year"] + 1))
        if opts["year"]:
            return [opts["year"]]
        raise CommandError("provide --year, or --start-year and --end-year.")

    def _sync_year(self, client, year, categories, opts) -> tuple[int, int]:
        cal = GroupedYearTournaments.model_validate(
            client.get_json(
                endpoints.vue_grouped_year_tournaments(year, categories=categories)
            )
        )
        tours = cal.all_tournaments()
        if opts["tiers"] == "senior":
            tours = [t for t in tours if _is_senior(t.category)]
        if opts["only"]:
            wanted = {int(x) for x in opts["only"].split(",") if x.strip()}
            tours = [t for t in tours if t.id in wanted]
        if opts["limit"]:
            tours = tours[: opts["limit"]]

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"{year}: {len(tours)} tournaments")
        )
        today = timezone.now().date()
        matches = failed = 0
        for t in tours:
            try:
                tournament = upsert_tournament_from_calendar(t)
                if opts["no_matches"] or not t.start or not t.end or t.start > today:
                    continue
                if opts["skip_collected"] and tournament.matches.exists():
                    continue
                if not t.code:  # day-matches needs the GUID
                    continue
                matches += self._collect_matches(client, tournament, t, today)
            except Exception:  # noqa: BLE001 - isolate one tournament, keep going
                logger.exception("skipping tournament %s (%s)", t.id, t.name)
                failed += 1
        if not opts["no_matches"]:
            self.stdout.write(
                f"  {year}: {matches} matches"
                + (f", {failed} tournaments failed" if failed else "")
            )
        return len(tours), matches

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
