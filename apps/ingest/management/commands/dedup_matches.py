"""`manage.py dedup_matches` — remove duplicate match rows.

Some tournaments were ingested via BOTH the draw-data and day-matches paths,
which assigned different match_ids to the same real contest — producing
duplicates that double-count in ratings. Two flavours occur:

  A. Same round label on both copies (e.g. the Olympics via two paths).
  B. One copy came in without round metadata (round_name='') while the other
     has the proper bracket round — so a naive (tournament, event, round,
     players) key misses them. These are matched on players + game scores,
     ignoring the round label.

A contest is identified by (tournament, event, {players}) plus — for case B —
the ordered game scores. The richest row is kept (prefers a real round label,
then a match time, then more games, then the lower id); the rest are deleted,
cascading their lineup / games / rating history / stats.

Dry-run by default; pass --apply to delete. Run the rating pipeline afterwards
(rate -> build_pairs -> build_analytics).
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.ingest.models import Game, Match, MatchPlayer


class Command(BaseCommand):
    help = "Delete duplicate matches (same contest under different match_ids)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Actually delete. Without this the command only reports.",
        )

    def handle(self, *args, **opts):
        players = defaultdict(set)
        for mid, pid in MatchPlayer.objects.values_list("match_id", "player_id"):
            players[mid].add(pid)

        scores = defaultdict(list)
        for mid, s1, s2 in (
            Game.objects.order_by("match_id", "game_no")
            .values_list("match_id", "side1_points", "side2_points")
        ):
            scores[mid].append((s1, s2))

        games_n = dict(
            Match.objects.annotate(g=Count("games")).values_list("match_id", "g")
        )
        meta = {
            m["match_id"]: m
            for m in Match.objects.values(
                "match_id", "tournament_id", "event", "round_name", "match_time_utc"
            ).iterator()
        }

        # Two signature schemes -> groups of match_ids for the same contest.
        groups = defaultdict(list)
        for mid, m in meta.items():
            pset = frozenset(players.get(mid, ()))
            if not pset:
                continue
            groups[("round", m["tournament_id"], m["event"], m["round_name"], pset)].append(mid)
            sc = tuple(scores.get(mid, ()))
            if sc:  # scores needed to safely match across round labels
                groups[("score", m["tournament_id"], m["event"], pset, sc)].append(mid)

        def keeprank(mid):
            m = meta[mid]
            return (
                m["round_name"] == "",          # keep rows that HAVE a round label
                m["match_time_utc"] is None,     # then rows with a real time
                -games_n.get(mid, 0),            # then more games
                mid,                              # then the lower id
            )

        keepers, candidates = set(), set()
        group_count = 0
        for key, mids in groups.items():
            uniq = list(dict.fromkeys(mids))
            if len(uniq) < 2:
                continue
            group_count += 1
            keep = min(uniq, key=keeprank)
            keepers.add(keep)
            candidates.update(m for m in uniq if m != keep)

        to_delete = sorted(candidates - keepers)
        blank_dups = sum(1 for mid in to_delete if meta[mid]["round_name"] == "")
        self.stdout.write(
            f"duplicate groups: {group_count}; matches to delete: {len(to_delete)} "
            f"({blank_dups} of them missing a round label)"
        )
        if not to_delete:
            return
        if not opts["apply"]:
            self.stdout.write("dry-run — pass --apply to delete.")
            return
        with transaction.atomic():
            Match.objects.filter(match_id__in=to_delete).delete()
        self.stdout.write(self.style.SUCCESS(f"deleted {len(to_delete)} duplicate matches."))
