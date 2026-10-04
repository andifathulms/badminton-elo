"""`manage.py offload_raw_cache` — move inline RawCache bodies to disk.

For every row that still stores its body in the database: write (or verify)
data/raw/<file>, then blank the column. Idempotent and resumable; batches keep
each transaction small. Afterwards run `VACUUM` (or `VACUUM INTO` a new file)
to hand the freed pages back to the OS.

    python manage.py offload_raw_cache
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import RawCache
from apps.ingest.rawstore import read_body, write_body


class Command(BaseCommand):
    help = "Move inline RawCache bodies to data/raw/ and blank the column."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **opts):
        moved = written = 0
        while True:
            batch = list(
                RawCache.objects.exclude(body="").values_list("url", "body")[
                    : opts["batch_size"]
                ]
            )
            if not batch:
                break
            with transaction.atomic():
                for url, body in batch:
                    if read_body(url) != body:
                        write_body(url, body)
                        written += 1
                    RawCache.objects.filter(pk=url).update(body="")
                    moved += 1
            self.stdout.write(f"  offloaded {moved} rows ({written} files written)")
        self.stdout.write(self.style.SUCCESS(
            f"done: {moved} rows offloaded, {written} files (re)written. "
            "Run VACUUM to reclaim the space."
        ))
