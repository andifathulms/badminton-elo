"""`manage.py build_pairs` — derive doubles/mixed partnerships (read-side).

The engine rates individuals, never pairs (PRD domain rule 5). This command
aggregates who played together (MD/WD/XD), how often, their record, and their
COMBINED current strength (mean mu, RMS rd of the two members) so pairs can be
ranked. Run after `rate` + `infer_gender`.

The pair's PEAK is the best combined rating the two reached in a match they
played TOGETHER (after that match, as for individual peaks; settled — rd <=
PEAK_MAX_RD — beats unsettled). Not the mean of each member's career peak:
that credits a five-match pairing with peaks both reached with other partners.
"""
from __future__ import annotations

import math
from collections import defaultdict

from django.conf import settings
from django.db import transaction

from apps.ingest.management.base import DataCommand
from apps.ingest.models import MatchPlayer, Partnership, Player, PlayerRating, RatingHistory

DOUBLES = ("MD", "WD", "XD")


class Command(DataCommand):
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
            lambda: {"matches": 0, "wins": 0, "utc": None, "peak": None, "raw": None}
        )
        # each member's rating right after every doubles match they played
        after = {
            (mid, pid): (mu, rd)
            for mid, pid, mu, rd in RatingHistory.objects.filter(
                event__in=DOUBLES).values_list("match_id", "player_id", "mu_after",
                                               "rd_after").iterator(chunk_size=50_000)
        }
        max_rd = settings.RATING.get("PEAK_MAX_RD", 100.0)
        for match_id, m in by_match.items():
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
                r1, r2 = after.get((match_id, players[0])), after.get((match_id, players[1]))
                if r1 and r2:
                    cand = ((r1[0] + r2[0]) / 2.0, math.sqrt((r1[1] ** 2 + r2[1] ** 2) / 2.0))
                    slot = "peak" if cand[1] <= max_rd else "raw"
                    if a[slot] is None or cand[0] > a[slot][0]:
                        a[slot] = cand

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

        # For a MIXED pair the convention is male first, female second (the pair
        # is keyed by sorted ids for dedup, but stored in gender order for display).
        genders = dict(
            Player.objects.exclude(gender="").values_list("player_id", "gender")
        )

        rows_out = []
        for (event, p1, p2), a in agg.items():
            if a["matches"] < min_matches:
                continue
            if event == "XD" and genders.get(p1) == "F" and genders.get(p2) == "M":
                p1, p2 = p2, p1
            r1 = ratings.get((p1, event))
            r2 = ratings.get((p2, event))
            if not r1 or not r2:
                continue
            peak_mu, peak_rd = a["peak"] or a["raw"] or (None, None)
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
