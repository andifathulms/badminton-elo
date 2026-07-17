"""`manage.py build_pairs` — derive doubles/mixed partnerships (read-side).

The engine rates individuals, never pairs (PRD domain rule 5). This command
aggregates who played together (MD/WD/XD), how often, their record, and their
COMBINED current strength (mean mu, RMS rd of the two members) so pairs can be
ranked. Run after `rate` + `infer_gender`.
"""
from __future__ import annotations

import math
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import MatchPlayer, Partnership, PlayerRating

DOUBLES = ("MD", "WD", "XD")


class Command(BaseCommand):
    help = "Aggregate doubles/mixed partnerships and their combined strength."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-matches",
            type=int,
            default=3,
            help="Only keep partnerships with at least N matches together.",
        )

    def handle(self, *args, **opts):
        min_matches = opts["min_matches"]

        # 1) group lineups by match to reconstruct each side's pair.
        by_match: dict[int, dict] = defaultdict(
            lambda: {"event": None, "winner": None, "utc": None, 1: [], 2: []}
        )
        rows = MatchPlayer.objects.filter(
            match__event__in=DOUBLES, match__rating_excluded=False
        ).values_list(
            "match_id",
            "side",
            "player_id",
            "match__event",
            "match__winner_side",
            "match__match_time_utc",
        )
        for match_id, side, pid, event, winner, utc in rows.iterator():
            m = by_match[match_id]
            m["event"], m["winner"], m["utc"] = event, winner, utc
            m[side].append(pid)

        # 2) aggregate partnerships (event, low_id, high_id).
        agg: dict = defaultdict(
            lambda: {"matches": 0, "wins": 0, "utc": None}
        )
        for m in by_match.values():
            for side in (1, 2):
                players = m[side]
                if len(players) != 2:
                    continue
                key = (m["event"], *sorted(players))
                a = agg[key]
                a["matches"] += 1
                if m["winner"] == side:
                    a["wins"] += 1
                if m["utc"] and (a["utc"] is None or m["utc"] > a["utc"]):
                    a["utc"] = m["utc"]

        # 3) combined current + peak strength from member ratings.
        ratings = {
            (pid, ev): (mu, rd, pmu, prd)
            for pid, ev, mu, rd, pmu, prd in PlayerRating.objects.filter(
                event__in=DOUBLES
            ).values_list("player_id", "event", "mu", "rd", "peak_mu", "peak_rd")
        }

        def blend(a, b):
            return (a + b) / 2.0

        def blend_rd(a, b):
            return math.sqrt((a * a + b * b) / 2.0)

        rows_out = []
        for (event, p1, p2), a in agg.items():
            if a["matches"] < min_matches:
                continue
            r1 = ratings.get((p1, event))
            r2 = ratings.get((p2, event))
            if not r1 or not r2:
                continue
            peak_mu = peak_rd = None
            if r1[2] is not None and r2[2] is not None:
                peak_mu = blend(r1[2], r2[2])
                peak_rd = blend_rd(r1[3], r2[3])
            rows_out.append(
                Partnership(
                    event=event,
                    player1_id=p1,
                    player2_id=p2,
                    matches_together=a["matches"],
                    wins_together=a["wins"],
                    combined_mu=blend(r1[0], r2[0]),
                    combined_rd=blend_rd(r1[1], r2[1]),
                    combined_peak_mu=peak_mu,
                    combined_peak_rd=peak_rd,
                    last_match_utc=a["utc"],
                )
            )

        with transaction.atomic():
            Partnership.objects.all().delete()
            Partnership.objects.bulk_create(rows_out, batch_size=2000)
        self.stdout.write(
            self.style.SUCCESS(
                f"built {len(rows_out)} partnerships (>= {min_matches} matches)."
            )
        )
