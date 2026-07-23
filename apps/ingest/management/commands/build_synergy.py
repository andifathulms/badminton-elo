"""`manage.py build_synergy` — partnership chemistry.

A pair's combined rating is just the mean of its two members — it says nothing
about whether they actually play better or worse *together*. This computes each
partnership's chess-style performance rating from its own results (the pair's
wins/losses vs the pre-match strength of the fields it faced), then

    synergy = perf_rating − combined_mu

Positive synergy means the duo overperforms the sum of its parts (real chemistry);
negative means they underperform their individual levels. Run after `rate` +
`build_pairs`.
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.management.commands.build_analytics import _perf_rating
from apps.ingest.models import MatchPlayer, Partnership, RatingHistory

DOUBLES = ("MD", "WD", "XD")


class Command(BaseCommand):
    help = "Compute partnership performance rating + synergy vs combined rating."

    def handle(self, *args, **opts):
        # Only pairs that already exist as Partnership rows need synergy.
        pairs = {
            (p.event, p.player1_id, p.player2_id): p
            for p in Partnership.objects.all()
        }
        if not pairs:
            self.stdout.write("no partnerships; run build_pairs first.")
            return

        # Reconstruct each doubles match's two sides + winner.
        by_match: dict = defaultdict(lambda: {"event": None, "winner": None, 1: [], 2: []})
        for mid, side, pid, ev, winner in MatchPlayer.objects.filter(
            match__event__in=DOUBLES, match__rating_excluded=False
        ).values_list(
            "match_id", "side", "player_id", "match__event", "match__winner_side"
        ).iterator():
            m = by_match[mid]
            m["event"], m["winner"] = ev, winner
            m[side].append(pid)

        # Pre-match rating per (match, player) — the opponent strength the engine saw.
        pre: dict = {}
        for mid, pid, mu_b in RatingHistory.objects.filter(
            event__in=DOUBLES
        ).values_list("match_id", "player_id", "mu_before").iterator():
            pre[(mid, pid)] = mu_b

        # Collect (opponent_field_rating, won) per partnership.
        results: dict = defaultdict(list)
        for mid, m in by_match.items():
            if m["winner"] not in (1, 2):
                continue
            for side in (1, 2):
                players = m[side]
                if len(players) != 2:
                    continue
                key = (m["event"], *sorted(players))
                if key not in pairs:
                    continue
                opp = m[2 if side == 1 else 1]
                opp_r = [pre[(mid, o)] for o in opp if (mid, o) in pre]
                if not opp_r:
                    continue
                results[key].append((sum(opp_r) / len(opp_r), m["winner"] == side))

        updates = []
        for key, res in results.items():
            p = pairs[key]
            perf = _perf_rating(res)
            if perf is None:
                continue
            p.perf_rating = perf
            p.synergy = round(perf - p.combined_mu, 1)
            updates.append(p)

        with transaction.atomic():
            Partnership.objects.bulk_update(
                updates, ["perf_rating", "synergy"], batch_size=2000
            )
        self.stdout.write(self.style.SUCCESS(f"set synergy on {len(updates)} pairs."))
