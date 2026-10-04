"""`manage.py build_ties` — precompute every team cup's ties (after `rate`).

Groups each team cup's rubbers into nation-vs-nation ties with each rubber's
ELO (apps.api.ties.build_ties) and stores the payload, so the Tournament page
for a Thomas/Uber/Sudirman Cup reads one row instead of regrouping hundreds of
rubbers per request.
"""
from __future__ import annotations

from django.db import transaction

from apps.api.ties import build_ties
from apps.api.views.common import team_cup_kind
from apps.ingest.management.base import DataCommand
from apps.ingest.models import Tournament, TournamentTies


class Command(DataCommand):
    help = "Precompute team-cup ties payloads."

    def handle(self, *args, **opts):
        rows = [
            TournamentTies(tournament=t, payload=build_ties(t))
            for t in Tournament.objects.filter(match_count__gt=0)
            if team_cup_kind(t) is not None
        ]
        with transaction.atomic():
            TournamentTies.objects.all().delete()
            TournamentTies.objects.bulk_create(rows, batch_size=200)
        self.stdout.write(self.style.SUCCESS(f"built ties for {len(rows)} team cups."))
