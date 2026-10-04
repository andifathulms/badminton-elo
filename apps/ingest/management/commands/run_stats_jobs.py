"""`manage.py run_stats_jobs` — drain the queued match-statistics fetches.

The web process drains the queue in a background thread on demand; this runs
the same loop from cron or a worker container (polite client, 1 QPS).

    python manage.py run_stats_jobs [--max N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ingest.statsjobs import drain


class Command(BaseCommand):
    help = "Fetch queued per-match rally statistics from BWF."

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=None, help="Stop after N jobs.")

    def handle(self, *args, **opts):
        ran = drain(opts["max"])
        self.stdout.write(self.style.SUCCESS(f"ran {ran} statistics fetch job(s)."))
