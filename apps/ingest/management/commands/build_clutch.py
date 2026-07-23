"""`manage.py build_clutch` — deciding-game ("clutch") record per player.

A match that reaches a third game went the distance; whoever advanced won the
decider. Aggregating those per (player, discipline) gives a clutch leaderboard:
who wins the tight ones. Only Normal matches count (a retirement in game three
isn't a contested decider). Overall matches/wins are kept for context. Depends
only on Game counts + winner_side, so coverage is every match, not just those
with rally stats.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import ClutchStat, Game, Match, MatchPlayer

EVENTS = ("MS", "WS", "MD", "WD", "XD")


class Command(BaseCommand):
    help = "Precompute deciding-game (clutch) records per player from match data."

    def handle(self, *args, **opts):
        # Games per match (a 3rd game == went the distance in the 3x* formats).
        game_counts: Counter = Counter()
        for (mid,) in Game.objects.values_list("match_id").iterator():
            game_counts[mid] += 1

        # Normal, decisive matches only, with their event + winner.
        meta = {
            mid: (event, winner)
            for mid, event, winner in Match.objects.filter(
                score_status="Normal", event__in=EVENTS, winner_side__in=(1, 2)
            ).values_list("match_id", "event", "winner_side").iterator()
        }

        agg: dict = defaultdict(lambda: [0, 0, 0, 0])  # dec_played, dec_won, matches, wins
        for mid, side, pid in MatchPlayer.objects.values_list(
            "match_id", "side", "player_id"
        ).iterator():
            info = meta.get(mid)
            if not info:
                continue
            event, winner = info
            a = agg[(pid, event)]
            won = 1 if side == winner else 0
            a[2] += 1
            a[3] += won
            if game_counts.get(mid, 0) >= 3:
                a[0] += 1
                a[1] += won

        objs = [
            ClutchStat(
                player_id=pid, event=event,
                deciders_played=a[0], deciders_won=a[1],
                matches=a[2], wins=a[3],
            )
            for (pid, event), a in agg.items()
            if a[0] > 0
        ]
        with transaction.atomic():
            ClutchStat.objects.all().delete()
            ClutchStat.objects.bulk_create(objs, batch_size=5000)
        self.stdout.write(self.style.SUCCESS(f"built {len(objs)} clutch records."))
