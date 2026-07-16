"""`manage.py scrape` — the Phase-1 ingestion driver (CLAUDE.md "Ingestion flow").

Flow per tournament:
  1. vue-tournament-detail  -> upsert Tournament (captures categoryModel.name = tier)
  2. vue-tournament-draws   -> upsert each main-draw Draw (qualification==0 unless
                               INCLUDE_QUALIFYING)
  3. vue-tournament-draw-data?draw={value} -> consume the flat `matches` array,
                               normalize into Match/MatchPlayer/Game rows
  4. scoring_format defaults from date (PRD §6.5) unless --scoring-format overrides

Every fetch goes through BwfClient (cache-first, rate-limited). Re-running is a
no-op: all writes upsert on stable ids.

    python manage.py scrape --code <GUID>
    python manage.py scrape --all               # settings.TOURNAMENT_CODES
    python manage.py scrape --code <GUID> --scoring-format 3x15 --no-cache
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import Draw
from apps.ingest.normalize import (
    normalize_draw_data,
    upsert_tournament,
)
from apps.ingest.schemas import DrawData, DrawInfo, TournamentDetail

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape BWF tournament(s): detail -> draws -> draw-data -> normalize."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--code", help="Tournament GUID to scrape.")
        group.add_argument(
            "--all",
            action="store_true",
            help="Scrape every code in settings.TOURNAMENT_CODES.",
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

        unconfirmed = endpoints.unconfirmed()
        if unconfirmed:
            self.stderr.write(
                self.style.WARNING(
                    "Endpoints with unconfirmed request params (verify vs network "
                    f"tab if a fetch 404s): {', '.join(unconfirmed)}"
                )
            )

        with BwfClient(use_cache=not opts["no_cache"]) as client:
            for code in codes:
                self._scrape_one(client, code, opts["scoring_format"])

    # -- per-tournament -----------------------------------------------------
    def _scrape_one(self, client: BwfClient, code: str, scoring_format: str | None):
        self.stdout.write(self.style.MIGRATE_HEADING(f"Scraping {code}"))

        # 1. detail -> Tournament
        detail_raw = client.get_json(endpoints.vue_tournament_detail(code))
        detail = TournamentDetail.model_validate(_results(detail_raw))
        tournament = upsert_tournament(detail)
        self.stdout.write(f"  tournament: {tournament.name} [{tournament.category_name}]")

        # 2. draws -> Draw (main draw only unless INCLUDE_QUALIFYING)
        draws_raw = client.get_json(endpoints.vue_tournament_draws(code))
        draw_rows = [DrawInfo.model_validate(d) for d in _results(draws_raw)]
        total_ingested = total_skipped = 0

        for info in draw_rows:
            if info.qualification != 0 and not settings.INCLUDE_QUALIFYING:
                continue
            draw = self._upsert_draw(tournament, info)

            # 3. draw-data -> matches
            data_raw = client.get_json(
                endpoints.vue_tournament_draw_data(code, info.value)
            )
            data = DrawData.model_validate(
                data_raw.get("results", data_raw)
                if isinstance(data_raw, dict) and "matches" not in data_raw
                else data_raw
            )
            ingested, skipped = normalize_draw_data(
                data,
                tournament=tournament,
                draw=draw,
                scoring_format_override=scoring_format,
            )
            total_ingested += ingested
            total_skipped += skipped
            self.stdout.write(
                f"  draw {info.value} [{info.text}]: {ingested} matches"
                + (f", {skipped} skipped" if skipped else "")
            )

        summary = f"Done {code}: {total_ingested} matches ingested"
        if total_skipped:
            summary += f", {total_skipped} skipped"
        self.stdout.write(self.style.SUCCESS(summary))

    def _upsert_draw(self, tournament, info: DrawInfo) -> Draw:
        draw, _ = Draw.objects.update_or_create(
            tournament=tournament,
            draw_value=info.value,
            defaults={
                "event": info.text,
                "stage": info.stage_name or ("Qualifying" if info.qualification else "Main Draw"),
                "doubles": info.doubles,
                "size": info.size,
            },
        )
        return draw


def _results(payload):
    """BWF wraps most responses in a `results` key; fall back to the payload."""
    if isinstance(payload, dict) and "results" in payload:
        return payload["results"]
    return payload
