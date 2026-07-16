"""`manage.py scrape_days` — collect a tournament via the day-matches endpoint.

day-matches is the only live-confirmed BWF endpoint (api/endpoints.CONFIRMED),
and it carries the full match shape across every discipline for a date. This
command iterates the tournament's dates and normalizes each day, which is how we
"collect as much data as we can" today, without the (currently 404) vue-* draw
endpoints.

    # explicit range
    python manage.py scrape_days --code <GUID> --start 2026-05-19 --end 2026-05-24
    # auto-expand outward from a known date until quiet on both ends
    python manage.py scrape_days --code <GUID> --seed 2026-05-24
    # every code in settings.TOURNAMENT_CODES (needs --seed or a range)
    python manage.py scrape_days --all --seed 2026-05-24

Cache-first and rate-limited via BwfClient, so re-running is a no-op.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.normalize import (
    normalize_day_matches,
    upsert_tournament_from_code,
)
from apps.ingest.schemas import DayMatches

logger = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


class Command(BaseCommand):
    help = "Collect a tournament's matches by iterating the day-matches endpoint."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--code", help="Tournament GUID.")
        group.add_argument(
            "--all",
            action="store_true",
            help="Every code in settings.TOURNAMENT_CODES.",
        )
        parser.add_argument("--start", type=_parse_date, help="First date (inclusive).")
        parser.add_argument("--end", type=_parse_date, help="Last date (inclusive).")
        parser.add_argument(
            "--seed",
            type=_parse_date,
            help="Known match date; auto-expands outward until quiet.",
        )
        parser.add_argument(
            "--max-empty",
            type=int,
            default=2,
            help="Consecutive empty days that end auto-expansion (default 2).",
        )
        parser.add_argument(
            "--scoring-format",
            default=None,
            help="Override scoring_format for all matches (e.g. 3x15).",
        )
        parser.add_argument(
            "--no-cache",
            action="store_true",
            help="Bypass RawCache and re-fetch from the network.",
        )

    def handle(self, *args, **opts):
        if opts["all"]:
            codes = list(settings.TOURNAMENT_CODES)
            if not codes:
                raise CommandError(
                    "settings.TOURNAMENT_CODES is empty; set it or use --code."
                )
        else:
            codes = [opts["code"]]

        if not opts["seed"] and not (opts["start"] and opts["end"]):
            raise CommandError(
                "provide either --start and --end, or --seed for auto-expansion."
            )

        with BwfClient(use_cache=not opts["no_cache"]) as client:
            for code in codes:
                self._scrape_one(client, code, opts)

    # -- per tournament -----------------------------------------------------
    def _scrape_one(self, client: BwfClient, code: str, opts) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"Collecting {code}"))

        if opts["seed"]:
            dates = self._expand_dates(client, code, opts["seed"], opts["max_empty"])
        else:
            dates = self._date_range(opts["start"], opts["end"])

        if not dates:
            self.stderr.write(self.style.WARNING(f"  no match days found for {code}"))
            return

        tournament = None
        total_ingested = total_skipped = 0
        for d in dates:
            matches = self._fetch_day(client, code, d)
            if not matches:
                continue
            if tournament is None:
                name = next((m.tournament_name for m in matches if m.tournament_name), "")
                tournament = upsert_tournament_from_code(code, name)
                self.stdout.write(f"  tournament: {tournament.name}")
            # Fill in real date span as we go.
            self._extend_span(tournament, d)
            ingested, skipped = normalize_day_matches(
                matches,
                tournament=tournament,
                scoring_format_override=opts["scoring_format"],
            )
            total_ingested += ingested
            total_skipped += skipped
            self.stdout.write(
                f"  {d}: {ingested} matches"
                + (f", {skipped} skipped" if skipped else "")
            )

        summary = f"Done {code}: {total_ingested} matches ingested over {len(dates)} day(s)"
        if total_skipped:
            summary += f", {total_skipped} skipped"
        self.stdout.write(self.style.SUCCESS(summary))

    # -- helpers ------------------------------------------------------------
    def _fetch_day(self, client: BwfClient, code: str, d: date):
        raw = client.get_json(endpoints.day_matches(code, d))
        if not isinstance(raw, list):
            logger.warning("day-matches %s %s: unexpected payload type", code, d)
            return []
        return DayMatches.validate_python(raw)

    def _date_range(self, start: date, end: date) -> list[date]:
        days = (end - start).days
        return [start + timedelta(days=i) for i in range(days + 1)]

    def _expand_dates(
        self, client: BwfClient, code: str, seed: date, max_empty: int
    ) -> list[date]:
        """Walk outward from the seed until max_empty consecutive empty days."""
        found: set[date] = set()

        def scan(step: int) -> None:
            empties = 0
            d = seed
            while empties < max_empty:
                matches = self._fetch_day(client, code, d)
                if matches:
                    found.add(d)
                    empties = 0
                else:
                    empties += 1
                d = d + timedelta(days=step)

        scan(+1)
        scan(-1)
        return sorted(found)

    def _extend_span(self, tournament, d: date) -> None:
        changed = False
        if tournament.start_date is None or d < tournament.start_date:
            tournament.start_date = d
            changed = True
        if tournament.end_date is None or d > tournament.end_date:
            tournament.end_date = d
            changed = True
        if changed:
            tournament.save(update_fields=["start_date", "end_date"])
