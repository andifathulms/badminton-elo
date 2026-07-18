"""Backfill MatchStatistics.max_comeback from stored point_progression.

Idempotent — recomputes the biggest-deficit-overcome for every stats row that
has a rally-by-rally progression. New rows get it at fetch time (h2h.py); this
covers rows captured before the field existed.
"""
from django.core.management.base import BaseCommand

from apps.ingest.h2h import max_comeback
from apps.ingest.models import MatchStatistics


class Command(BaseCommand):
    help = "Compute max_comeback for MatchStatistics rows with point_progression."

    def handle(self, *args, **opts):
        qs = MatchStatistics.objects.exclude(point_progression=None).iterator()
        updated = 0
        batch = []
        for st in qs:
            mc = max_comeback(st.point_progression)
            if mc != st.max_comeback:
                st.max_comeback = mc
                batch.append(st)
            if len(batch) >= 500:
                MatchStatistics.objects.bulk_update(batch, ["max_comeback"])
                updated += len(batch)
                batch = []
        if batch:
            MatchStatistics.objects.bulk_update(batch, ["max_comeback"])
            updated += len(batch)
        self.stdout.write(self.style.SUCCESS(f"Updated max_comeback on {updated} rows."))
