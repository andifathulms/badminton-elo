"""`manage.py build_analytics` — precompute browsable analytics from ratings.

Aggregates RatingHistory into per-(player, event, tournament) performances:
net rating change, matches, start/end rating, and the single biggest-gain match
(the standout win). Powers the Insights page (biggest tournament gains, upsets).
Run after `rate`.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import MatchPlayer, RatingHistory, TournamentPerformance

DOUBLES = ("MD", "WD", "XD")


class Command(BaseCommand):
    help = "Precompute per-tournament performance analytics from RatingHistory."

    def _partners(self) -> dict:
        """(player, event, tournament) -> main doubles partner id."""
        by_side = defaultdict(list)
        rows = MatchPlayer.objects.filter(match__event__in=DOUBLES).values_list(
            "match_id", "side", "player_id", "match__event", "match__tournament_id"
        )
        for mid, side, pid, ev, tid in rows.iterator():
            by_side[(mid, side)].append((pid, ev, tid))
        counts = defaultdict(Counter)
        for players in by_side.values():
            if len(players) == 2:
                (p1, ev, tid), (p2, _, _) = players
                counts[(p1, ev, tid)][p2] += 1
                counts[(p2, ev, tid)][p1] += 1
        return {k: c.most_common(1)[0][0] for k, c in counts.items()}

    def handle(self, *args, **opts):
        partners = self._partners()
        # Group history rows by (player, event, tournament).
        agg: dict = defaultdict(
            lambda: {"net": 0.0, "n": 0, "start": None, "rd_start": None,
                     "end_after": None, "best_delta": None, "best_match": None,
                     "last_order": -1}
        )
        rows = RatingHistory.objects.select_related("match").values_list(
            "player_id", "event", "match__tournament_id", "match_id",
            "match__round_order", "mu_before", "mu_after", "delta", "rd_before",
        )
        for pid, ev, tid, mid, rorder, before, after, delta, rd_before in rows.iterator():
            if tid is None:
                continue
            a = agg[(pid, ev, tid)]
            a["net"] += delta
            a["n"] += 1
            if a["start"] is None:
                a["start"] = before
                a["rd_start"] = rd_before
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
                rd_start=a["rd_start"] if a["rd_start"] is not None else 350.0,
                best_match_id=a["best_match"],
                best_delta=a["best_delta"],
                partner_id=partners.get((pid, ev, tid)),
            )
            for (pid, ev, tid), a in agg.items()
        ]
        with transaction.atomic():
            TournamentPerformance.objects.all().delete()
            TournamentPerformance.objects.bulk_create(objs, batch_size=5000)
        self.stdout.write(
            self.style.SUCCESS(f"built {len(objs)} tournament performances.")
        )
