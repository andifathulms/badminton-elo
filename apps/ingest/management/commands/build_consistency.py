"""`manage.py build_consistency` — per-player form volatility.

The standard deviation of a player's per-match rating deltas measures how steady
their form is: a low value means results rarely surprise their rating (predictable),
a high value means big swings (giant-killings and bad losses). Computed per
(player, discipline) from RatingHistory in a single streaming pass and written
back onto PlayerRating.volatility. Run after `rate`.
"""
from __future__ import annotations

import math
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import PlayerRating, RatingHistory


class Command(BaseCommand):
    help = "Compute per-player rating-delta volatility onto PlayerRating."

    def handle(self, *args, **opts):
        # Streaming variance accumulators per (player, event): n, Σx, Σx².
        acc: dict = defaultdict(lambda: [0, 0.0, 0.0])
        for pid, ev, delta in RatingHistory.objects.values_list(
            "player_id", "event", "delta"
        ).iterator():
            a = acc[(pid, ev)]
            a[0] += 1
            a[1] += delta
            a[2] += delta * delta

        vol = {}
        for key, (n, s, ss) in acc.items():
            if n >= 2:
                var = max(0.0, ss / n - (s / n) ** 2)  # population variance
                vol[key] = round(math.sqrt(var), 2)

        updates = []
        for r in PlayerRating.objects.all().iterator():
            v = vol.get((r.player_id, r.event))
            if r.volatility != v:
                r.volatility = v
                updates.append(r)

        with transaction.atomic():
            PlayerRating.objects.bulk_update(updates, ["volatility"], batch_size=5000)
        self.stdout.write(
            self.style.SUCCESS(f"set volatility on {len(updates)} ratings.")
        )
