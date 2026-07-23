"""`manage.py build_calibration` — reliability of the rating's predictions.

For every rated match, reconstruct both sides' pre-match team rating from the
RatingHistory rows (mu_before / rd_before — the tournament-locked figure the
engine actually predicted from), compute the favorite's win probability, and
record whether that favorite won. Bucketed by predicted probability, this is a
reliability diagram: a well-calibrated rating that says "72%" should win ~72% of
those matches. Run after `rate`.
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.api.predict import team_rating, win_probability
from apps.ingest.models import CalibrationBin, Match, MatchPlayer, RatingHistory


class Command(BaseCommand):
    help = "Precompute rating reliability (predicted vs actual) from RatingHistory."

    def handle(self, *args, **opts):
        # sides per match, from the lineup.
        sides = defaultdict(lambda: {1: [], 2: []})
        for mid, side, pid in MatchPlayer.objects.values_list(
            "match_id", "side", "player_id"
        ).iterator():
            sides[mid][side].append(pid)
        winner = dict(Match.objects.values_list("match_id", "winner_side").iterator())

        # Pre-match (mu, rd) per (match, player) from the history rows.
        pre: dict = defaultdict(dict)  # match_id -> {player_id: (mu, rd)}
        ev: dict = {}
        for mid, pid, event, mu_b, rd_b in RatingHistory.objects.values_list(
            "match_id", "player_id", "event", "mu_before", "rd_before"
        ).iterator():
            pre[mid][pid] = (mu_b, rd_b)
            ev[mid] = event

        # bucket -> [n, correct, prob_sum], per event and pooled ("ALL").
        bins: dict = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))
        for mid, players in pre.items():
            win = winner.get(mid)
            if win not in (1, 2):
                continue
            s1 = [players[p] for p in sides[mid][1] if p in players]
            s2 = [players[p] for p in sides[mid][2] if p in players]
            t1, t2 = team_rating(s1), team_rating(s2)
            if not t1 or not t2:
                continue
            p1 = win_probability(t1[0], t1[1], t2[0], t2[1])
            # Favorite's predicted prob (>= .5) and whether the favorite won.
            fav_side = 1 if p1 >= 0.5 else 2
            fav_p = p1 if fav_side == 1 else 1.0 - p1
            correct = 1 if win == fav_side else 0
            bucket = min(9, int(fav_p * 10))
            event = ev[mid]
            for key in (event, "ALL"):
                b = bins[key][bucket]
                b[0] += 1
                b[1] += correct
                b[2] += fav_p

        objs = [
            CalibrationBin(event=event, bucket=bucket, n=b[0], correct=b[1], prob_sum=b[2])
            for event, buckets in bins.items()
            for bucket, b in buckets.items()
        ]
        with transaction.atomic():
            CalibrationBin.objects.all().delete()
            CalibrationBin.objects.bulk_create(objs, batch_size=1000)
        total = bins["ALL"]
        n = sum(b[0] for b in total.values())
        ok = sum(b[1] for b in total.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"built {len(objs)} calibration bins · {ok}/{n} favorites won "
                f"({100.0 * ok / n:.1f}% accuracy)" if n else "no rated matches"
            )
        )
