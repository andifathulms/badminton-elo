"""One-time fix: give Wikipedia-sourced tournaments/matches chronological dates.

Early ingests left some wiki tournaments with a null start_date (their infobox
had no parseable date and predated the year-in-title fallback) and every wiki
match with a null match_time_utc. Both break chronology — the rating engine
processed those matches as if they happened in year 1, and history sorted by
ingestion order. This sets start_date from the year in the title and derives
each match's time from the tournament date + round. Re-rate afterwards.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_tz

from django.core.management.base import BaseCommand

from apps.ingest.models import Match, Tournament

YEAR = re.compile(r"(\d{4})")


class Command(BaseCommand):
    help = "Backfill start_date + match_time_utc for Wikipedia-sourced data."

    def handle(self, *args, **opts):
        fixed_t = 0
        for t in Tournament.objects.filter(code__startswith="wiki:", start_date=None):
            m = YEAR.search(t.code)
            if m:
                t.start_date = date(int(m.group(1)), 6, 1)
                t.end_date = t.end_date or t.start_date
                t.save(update_fields=["start_date", "end_date"])
                fixed_t += 1

        fixed_m = 0
        batch = []
        qs = (Match.objects.filter(source_key__startswith="wiki:")
              .select_related("tournament").iterator())
        for mt in qs:
            sd = mt.tournament.start_date
            want = (datetime.combine(sd, dt_time(), tzinfo=dt_tz.utc)
                    + timedelta(minutes=mt.round_order or 0)) if sd else None
            if want != mt.match_time_utc:
                mt.match_time_utc = want
                batch.append(mt)
            if len(batch) >= 1000:
                Match.objects.bulk_update(batch, ["match_time_utc"]); fixed_m += len(batch); batch = []
        if batch:
            Match.objects.bulk_update(batch, ["match_time_utc"]); fixed_m += len(batch)

        self.stdout.write(self.style.SUCCESS(
            f"Set start_date on {fixed_t} tournaments, match_time on {fixed_m} matches. "
            f"Run `rate --rebuild` next."))
