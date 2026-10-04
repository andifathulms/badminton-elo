"""Give Wikipedia-sourced tournaments/matches chronological dates.

Early ingests left some wiki tournaments with a null start_date (their infobox
had no parseable date and predated the year-in-title fallback) and every wiki
match with a null match_time_utc. Both break chronology — the rating engine
processed those matches as if they happened in year 1, and history sorted by
ingestion order. This sets start_date from the year in the title and derives
each match's time from the tournament date + round. Re-rate afterwards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_tz


from apps.ingest.management.base import DataCommand
from apps.ingest.models import Match, Tournament

YEAR = re.compile(r"(\d{4})")


class Command(DataCommand):
    help = "Backfill start_date + match_time_utc for Wikipedia-sourced data."

    def handle(self, *args, **opts):
        from apps.ingest.management.commands.scrape_wiki import YEAR_RE, infobox_meta
        from apps.ingest.wiki_client import CACHE_DIR

        fixed_t = 0
        for t in Tournament.objects.filter(code__startswith="wiki:"):
            title = t.code[len("wiki:"):]
            ym = YEAR_RE.search(title)
            year = int(ym.group(0)) if ym else None
            # Re-derive from the cached article's infobox (the parser used to
            # read stray {{Start date}}s / '{{Use dmy dates|date=…}}' tags).
            cp = Path(CACHE_DIR) / (title.replace("/", "_").replace(" ", "_") + ".json")
            start = None
            if cp.exists():
                wt = json.loads(cp.read_text()).get("wikitext") or ""
                start = infobox_meta(wt, year)["start"]
            if start is None and t.start_date is None and year:
                start = date(year, 6, 1)
            if start and start != t.start_date:
                t.start_date = start
                t.end_date = start if not t.end_date or t.end_date < start else t.end_date
                t.save(update_fields=["start_date", "end_date"])
                fixed_t += 1

        fixed_m = 0
        batch = []
        # A list, not .iterator(): bulk_update commits mid-loop, which closes
        # SQLite's open read cursor ("Cannot operate on a closed database").
        qs = list(Match.objects.filter(source_key__startswith="wiki:")
                  .select_related("tournament").only(
                      "match_id", "round_order", "match_time_utc", "tournament__start_date"))
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
