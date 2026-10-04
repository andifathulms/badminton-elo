"""`manage.py fix_scoring_formats` — label pre-2006 side-out matches correctly.

Before rally scoring (2006) games were side-out: 15 points (11 in women's
singles), extendable to 18 at 13-all; 2001-02 trialled best-of-5 to 7. The
Wikipedia backfill labelled those '3x15'/'3x11' — rally-point formats, which
the points engine reads rally by rally (rating/points.RALLY_FORMATS). This
relabels them from the games themselves: >= 3 games all <= 10 points ->
'5x7'; every game <= 18 -> '15x3s'; anything reaching 19+ stays rally.
Idempotent; part of the refresh pipeline.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from apps.ingest.management.base import DataCommand
from apps.ingest.models import Game, Match

RALLY_CUTOFF = date(2006, 1, 1)


def side_out_code(maxes: list[int]) -> str | None:
    if len(maxes) >= 3 and max(maxes) <= 10:
        return "5x7"
    if maxes and max(maxes) <= 18:
        return "15x3s"
    return None


class Command(DataCommand):
    help = "Relabel pre-2006 side-out matches (not rally formats)."

    def handle(self, *args, **opts):
        ids = list(Match.objects.filter(tournament__start_date__lt=RALLY_CUTOFF)
                   .exclude(scoring_format__in=("15x3s", "5x7"))
                   .values_list("match_id", flat=True))
        maxes = defaultdict(list)
        for i in range(0, len(ids), 5000):
            for mid, a, b in Game.objects.filter(match_id__in=ids[i:i + 5000]).values_list(
                    "match_id", "side1_points", "side2_points"):
                maxes[mid].append(max(a, b))
        by_code = defaultdict(list)
        for mid, mx in maxes.items():
            code = side_out_code(mx)
            if code:
                by_code[code].append(mid)
        for code, mids in by_code.items():
            for i in range(0, len(mids), 5000):
                Match.objects.filter(match_id__in=mids[i:i + 5000]).update(scoring_format=code)
        self.stdout.write(self.style.SUCCESS(
            "relabelled " + ", ".join(f"{len(v)} -> {k}" for k, v in by_code.items())
            if by_code else "nothing to relabel"))
