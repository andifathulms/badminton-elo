"""`manage.py dedup_tournaments` — merge Wikipedia copies into API tournaments.

For each tournament ingested from BOTH Wikipedia and the BWF API
(apps/ingest/dedup.py): delete the Wikipedia matches that duplicate API
matches (and any bye pseudo-matches), move the genuinely extra ones (e.g. the
2023 Sudirman Cup group ties the API lacks) into the API tournament, drop
extras with impossible scores, and delete the emptied Wikipedia tournament.

Dry-run by default; --apply to change data. Run `rate` afterwards.
"""
from __future__ import annotations

from django.db import transaction

from apps.ingest.dedup import SOURCES, find_pairs
from apps.ingest.management.base import DataCommand
from apps.ingest.models import Match, Tournament


class Command(DataCommand):
    help = "Merge tournaments ingested from both Wikipedia and the BWF API."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        # German copies first (vs the API), then English (vs API + German), then
        # German finals-only copies (vs anything fuller).
        pairs = []
        for source, weaker, small in SOURCES:
            found = find_pairs(source, weaker, small)
            if opts["apply"] and found:
                self._apply(found)
            pairs += found
        totals = {"dup": 0, "bye": 0, "move": 0, "drop": 0}
        for w, a, plan in pairs:
            target = f"{a.name[:45]!r} [{a.tournament_id}]" if a else "(API events it contains)"
            self.stdout.write(
                f"{w.name[:45]!r} [{w.tournament_id}] -> {target}: "
                + ", ".join(f"{k} {len(v)}" for k, v in plan.items())
            )
            for k, v in plan.items():
                totals[k] += len(v)
        self.stdout.write(f"{len(pairs)} duplicate tournaments; " +
                          ", ".join(f"{k} {v}" for k, v in totals.items()))
        if not opts["apply"]:
            self.stdout.write("dry run — pass --apply to merge.")
            return
        self.stdout.write(self.style.SUCCESS("merged."))

    @transaction.atomic
    def _apply(self, pairs):
        for w, a, plan in pairs:
            gone = [mid for k in ("dup", "bye", "drop") for mid in plan[k]]
            Match.objects.filter(match_id__in=gone).delete()
            if a is not None:
                Match.objects.filter(match_id__in=plan["move"]).update(
                    tournament_id=a.tournament_id, draw=None
                )
            if not Match.objects.filter(tournament_id=w.tournament_id).exists():
                Tournament.objects.filter(pk=w.tournament_id).delete()
