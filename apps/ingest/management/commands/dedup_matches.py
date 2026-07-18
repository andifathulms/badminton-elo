"""`manage.py dedup_matches` — remove duplicate match rows.

A few tournaments (e.g. the Olympics) were ingested via BOTH the draw-data and
day-matches paths, which assigned different match_ids to the same real match —
producing duplicates that double-count in ratings. Two matches are the same
contest when they share (tournament, event, round, the set of players). The
richest row is kept (prefers a real match time, then more games, then the lower
id); the rest are deleted (cascading their lineup/games/history/stats).

Run `rate` afterwards.
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.ingest.models import Match, MatchPlayer


class Command(BaseCommand):
    help = "Delete duplicate matches (same tournament/event/round/players)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        # player set per match
        players = defaultdict(set)
        for mid, pid in MatchPlayer.objects.values_list("match_id", "player_id"):
            players[mid].add(pid)

        # signature -> list of match rows
        sig = defaultdict(list)
        games = dict(
            Match.objects.annotate(g=Count("games")).values_list("match_id", "g")
        )
        for m in Match.objects.values(
            "match_id", "tournament_id", "event", "round_name", "match_time_utc"
        ).iterator():
            mid = m["match_id"]
            key = (
                m["tournament_id"],
                m["event"],
                m["round_name"],
                frozenset(players.get(mid, ())),
            )
            sig[key].append((mid, m["match_time_utc"], games.get(mid, 0)))

        to_delete = []
        for rows in sig.values():
            if len(rows) < 2:
                continue
            # keep: has time > more games > lower id
            keep = sorted(
                rows, key=lambda r: (r[1] is None, -r[2], r[0])
            )[0]
            to_delete += [mid for mid, _, _ in rows if mid != keep[0]]

        self.stdout.write(
            f"duplicate groups: {sum(1 for r in sig.values() if len(r) > 1)}; "
            f"matches to delete: {len(to_delete)}"
        )
        if opts["dry_run"] or not to_delete:
            return
        with transaction.atomic():
            deleted, _ = Match.objects.filter(match_id__in=to_delete).delete()
        self.stdout.write(
            self.style.SUCCESS(f"deleted {len(to_delete)} duplicate matches.")
        )
