"""`manage.py build_analytics` — precompute browsable analytics from ratings.

Aggregates RatingHistory into per-(player, event, tournament) performances: net
rating change, matches, start/end rating, the standout win, the main doubles
partner, and a chess-style PERFORMANCE RATING (the rating at which the player's/
pair's results against that tournament's field of opponents would be expected —
so beating a strong field scores higher than an easy title). Run after `rate`.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import Match, MatchPlayer, RatingHistory, TournamentPerformance

DOUBLES = ("MD", "WD", "XD")


def _perf_rating(results: list[tuple[float, bool]]) -> float | None:
    """Rating R where expected score vs the field == actual wins (bisection)."""
    if not results:
        return None
    wins = sum(1 for _, w in results if w)
    n = len(results)
    if wins == 0:
        return min(r for r, _ in results) - 400.0
    if wins == n:
        return max(r for r, _ in results) + 400.0
    lo, hi = 0.0, 4000.0
    for _ in range(42):
        mid = (lo + hi) / 2.0
        exp = sum(1.0 / (1.0 + 10.0 ** ((r - mid) / 400.0)) for r, _ in results)
        if exp < wins:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 1)


class Command(BaseCommand):
    help = "Precompute per-tournament performance analytics from RatingHistory."

    def _match_data(self):
        """(sides per match, winner per match) for every rated match."""
        sides = defaultdict(lambda: {1: [], 2: []})
        for mid, side, pid in MatchPlayer.objects.values_list(
            "match_id", "side", "player_id"
        ).iterator():
            sides[mid][side].append(pid)
        winner = dict(
            Match.objects.values_list("match_id", "winner_side").iterator()
        )
        return sides, winner

    def _partners(self, sides) -> dict:
        """(player, event, tournament) -> main doubles partner id."""
        meta = dict(
            Match.objects.filter(event__in=DOUBLES).values_list(
                "match_id", "event"
            )
        )
        tmap = dict(
            Match.objects.filter(event__in=DOUBLES).values_list(
                "match_id", "tournament_id"
            )
        )
        counts = defaultdict(Counter)
        for mid, ev in meta.items():
            tid = tmap.get(mid)
            for side in (1, 2):
                players = sides.get(mid, {}).get(side, [])
                if len(players) == 2:
                    a, b = players
                    counts[(a, ev, tid)][b] += 1
                    counts[(b, ev, tid)][a] += 1
        return {k: c.most_common(1)[0][0] for k, c in counts.items()}

    def handle(self, *args, **opts):
        sides, winner = self._match_data()
        partners = self._partners(sides)

        # Pass 1: per (player, event, tournament) aggregate + mu_start.
        agg: dict = defaultdict(
            lambda: {"net": 0.0, "n": 0, "start": None, "rd_start": None,
                     "end_after": None, "best_delta": None, "best_match": None,
                     "last_order": -1}
        )
        rows = RatingHistory.objects.values_list(
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
            if (rorder or 0) >= a["last_order"]:
                a["last_order"] = rorder or 0
                a["end_after"] = after
            if a["best_delta"] is None or delta > a["best_delta"]:
                a["best_delta"] = delta
                a["best_match"] = mid

        start = {k: a["start"] for k, a in agg.items() if a["start"] is not None}

        # Pass 2: performance rating — opponents' start ratings + win/loss.
        perf_inputs = defaultdict(list)
        for pid, ev, tid, mid in RatingHistory.objects.values_list(
            "player_id", "event", "match__tournament_id", "match_id"
        ).iterator():
            if tid is None:
                continue
            side = 1 if pid in sides.get(mid, {}).get(1, []) else 2
            opp_ids = sides.get(mid, {}).get(2 if side == 1 else 1, [])
            opp_r = [start.get((o, ev, tid)) for o in opp_ids]
            opp_r = [r for r in opp_r if r is not None]
            if not opp_r:
                continue
            perf_inputs[(pid, ev, tid)].append(
                (sum(opp_r) / len(opp_r), winner.get(mid) == side)
            )

        perf = {k: _perf_rating(v) for k, v in perf_inputs.items()}

        objs = [
            TournamentPerformance(
                player_id=pid, event=ev, tournament_id=tid,
                net_delta=a["net"], matches=a["n"],
                mu_start=a["start"] if a["start"] is not None else 0.0,
                mu_end=a["end_after"] if a["end_after"] is not None else 0.0,
                rd_start=a["rd_start"] if a["rd_start"] is not None else 350.0,
                best_match_id=a["best_match"], best_delta=a["best_delta"],
                perf_rating=perf.get((pid, ev, tid)),
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
