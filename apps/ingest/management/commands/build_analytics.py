"""`manage.py build_analytics` — precompute browsable analytics from ratings.

Aggregates RatingHistory into per-(player, event, tournament) performances:
net rating change, matches, start/end rating, and the single biggest-gain match
(the standout win). Powers the Insights page (biggest tournament gains, upsets).
Run after `rate`.
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import RatingHistory, TournamentPerformance


class Command(BaseCommand):
    help = "Precompute per-tournament performance analytics from RatingHistory."

    def handle(self, *args, **opts):
        # Group history rows by (player, event, tournament).
        agg: dict = defaultdict(
            lambda: {"net": 0.0, "n": 0, "start": None, "end_delta": None,
                     "end_after": None, "best_delta": None, "best_match": None,
                     "last_order": -1}
        )
        rows = RatingHistory.objects.select_related("match").values_list(
            "player_id", "event", "match__tournament_id", "match_id",
            "match__round_order", "mu_before", "mu_after", "delta",
        )
        for pid, ev, tid, mid, rorder, before, after, delta in rows.iterator():
            if tid is None:
                continue
            a = agg[(pid, ev, tid)]
            a["net"] += delta
            a["n"] += 1
            a["start"] = before if a["start"] is None else a["start"]
            # end = mu_after of the last match by round order
            if rorder is None:
                rorder = 0
            if rorder >= a["last_order"]:
                a["last_order"] = rorder
                a["end_after"] = after
            if a["best_delta"] is None or delta > a["best_delta"]:
                a["best_delta"] = delta
                a["best_match"] = mid

        objs = [
            TournamentPerformance(
                player_id=pid,
                event=ev,
                tournament_id=tid,
                net_delta=a["net"],
                matches=a["n"],
                mu_start=a["start"] if a["start"] is not None else 0.0,
                mu_end=a["end_after"] if a["end_after"] is not None else 0.0,
                best_match_id=a["best_match"],
                best_delta=a["best_delta"],
            )
            for (pid, ev, tid), a in agg.items()
        ]
        with transaction.atomic():
            TournamentPerformance.objects.all().delete()
            TournamentPerformance.objects.bulk_create(objs, batch_size=5000)
        self.stdout.write(
            self.style.SUCCESS(f"built {len(objs)} tournament performances.")
        )
