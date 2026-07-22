"""Correct the stored discipline on team-cup rubbers.

Team-cup articles list rubbers in play order and the scraper labels them by
POSITION, so a rubber's `event` often doesn't match who actually played (e.g. a
singles match stored as MD). That mislabelling misroutes ratings — a player's
singles win lands in their doubles bucket. This command re-derives each cup
rubber's discipline from its lineup + player gender (apps.ingest.cup_events) and
updates Match.event where it can tell. Run `rate --rebuild` + build_* afterwards.

    python manage.py fix_cup_events            # apply
    python manage.py fix_cup_events --dry-run  # report only
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.ingest.cup_events import rubber_discipline
from apps.ingest.models import Match, Tournament

# Same detection as the API's team_cup_kind, kept here so ingest has no api dep.
CUP_TERMS = ("sudirman cup", "thomas cup", "uber cup", "team championship")


def team_cup_tournaments():
    q = Q()
    for term in CUP_TERMS:
        q |= Q(name__icontains=term) | Q(category_name__icontains=term)
    return Tournament.objects.filter(q)


class Command(BaseCommand):
    help = "Fix mislabelled disciplines on team-cup rubbers (from the lineup)."

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true",
                       help="report changes without writing")

    def handle(self, *a, **o):
        tour_ids = list(team_cup_tournaments().values_list("tournament_id", flat=True))
        self.stdout.write(f"{len(tour_ids)} team-cup tournaments")
        changed = 0
        undetermined = 0
        moves: Counter = Counter()
        # Per tournament — a single filter over 200+ tournaments blows SQLite's
        # expression-depth limit.
        for tid in tour_ids:
            to_update = []
            for m in (
                Match.objects.filter(tournament_id=tid)
                .prefetch_related("lineup__player")
            ):
                s1 = [l.player for l in m.lineup.all() if l.side == 1]
                s2 = [l.player for l in m.lineup.all() if l.side == 2]
                disc = rubber_discipline(s1, s2)
                if disc is None:
                    undetermined += 1
                    continue
                if disc != m.event:
                    moves[f"{m.event or '—'}→{disc}"] += 1
                    changed += 1
                    m.event = disc
                    to_update.append(m)
            if not o["dry_run"] and to_update:
                Match.objects.bulk_update(to_update, ["event"], batch_size=1000)

        verb = "would change" if o["dry_run"] else "changed"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {changed} rubbers; {undetermined} undetermined (gender unknown)"))
        for mv, n in moves.most_common():
            self.stdout.write(f"  {mv}: {n}")
