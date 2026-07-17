"""`manage.py scrape` — draw-level ingestion via the PRIMARY results source.

Now that the vue-tournament-* endpoints are confirmed (keyed by the numeric
tmtId), this is the authoritative per-tournament flow (CLAUDE.md "Ingestion
flow"):

  1. vue-tournament-detail?tmtId=  -> upsert Tournament (full metadata + tier)
  2. vue-tournament-draws?tmtId=    -> upsert each Draw (with qualification flag)
  3. vue-tournament-draw-data?...&drawId= -> flat `matches` array -> normalize
  4. scoring_format defaults from date (PRD §6.5) unless --scoring-format

Unlike day-matches, this associates every match with its Draw and knows which
draws are qualifying, so main-draw filtering is exact.

    python manage.py scrape --id 5229
    python manage.py scrape --code 71AC3AB2-...        # resolves id via the DB
    python manage.py scrape --all                       # every Tournament in the DB
    python manage.py scrape --id 5229 --include-qualifying
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import Draw, Tournament
from apps.ingest.normalize import normalize_draw_data, upsert_tournament
from apps.ingest.schemas import DrawData, DrawInfo, TournamentDetail

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape a tournament's draws/draw-data (detail -> draws -> draw-data)."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--id", type=int, help="Numeric tournament id (tmtId).")
        group.add_argument("--code", help="Tournament GUID (resolved to id via the DB).")
        group.add_argument(
            "--all",
            action="store_true",
            help="Every Tournament already in the DB (run sync_calendar first).",
        )
        parser.add_argument(
            "--include-qualifying",
            action="store_true",
            help="Also ingest qualifying draws (default: main draw only).",
        )
        parser.add_argument("--scoring-format", default=None)
        parser.add_argument("--no-cache", action="store_true")

    def handle(self, *args, **opts):
        ids = self._resolve_ids(opts)
        include_qual = opts["include_qualifying"] or settings.INCLUDE_QUALIFYING
        with BwfClient(use_cache=not opts["no_cache"]) as client:
            for tmt_id in ids:
                self._scrape_one(
                    client, tmt_id, include_qual, opts["scoring_format"]
                )

    def _resolve_ids(self, opts) -> list[int]:
        if opts["all"]:
            ids = list(
                Tournament.objects.order_by("start_date").values_list(
                    "tournament_id", flat=True
                )
            )
            if not ids:
                raise CommandError("no tournaments in the DB; run sync_calendar first.")
            return ids
        if opts["code"]:
            t = Tournament.objects.filter(code=opts["code"]).first()
            if not t:
                raise CommandError(
                    f"code {opts['code']} not found; run sync_calendar or use --id."
                )
            return [t.tournament_id]
        return [opts["id"]]

    # -- per tournament -----------------------------------------------------
    def _scrape_one(self, client, tmt_id, include_qual, scoring_format):
        # 1. detail
        detail_raw = _results(client.get_json(endpoints.vue_tournament_detail(tmt_id)))
        detail = TournamentDetail.model_validate(detail_raw)
        tournament = upsert_tournament(detail)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"[{tmt_id}] {tournament.name} ({tournament.category_name})"
            )
        )

        # 2. draws
        draws_raw = _results(client.get_json(endpoints.vue_tournament_draws(tmt_id)))
        draw_rows = [DrawInfo.model_validate(d) for d in draws_raw]
        total_ingested = total_skipped = 0

        for info in draw_rows:
            if info.qualification != 0 and not include_qual:
                continue
            draw = self._upsert_draw(tournament, info)

            # 3. draw-data -> flat matches array
            data = DrawData.model_validate(
                client.get_json(endpoints.vue_tournament_draw_data(tmt_id, info.value))
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

        summary = f"  -> {total_ingested} matches"
        if total_skipped:
            summary += f", {total_skipped} skipped"
        self.stdout.write(self.style.SUCCESS(summary))

    def _upsert_draw(self, tournament, info: DrawInfo) -> Draw:
        draw, _ = Draw.objects.update_or_create(
            tournament=tournament,
            draw_value=info.value,
            defaults={
                "event": info.event,
                "stage": info.stage_name
                or ("Qualifying" if info.qualification else "Main Draw"),
                "doubles": info.doubles,
                "size": info.size,
            },
        )
        return draw


def _results(payload):
    """vue-* responses wrap the body in `results`; fall back to the payload."""
    if isinstance(payload, dict) and "results" in payload:
        return payload["results"]
    return payload
