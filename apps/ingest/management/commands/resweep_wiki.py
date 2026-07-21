"""Re-ingest every already-scraped Wikipedia tournament from cache.

Use this after fixing the bracket parser (apps.ingest.wiki_parse) to purge
corrupted matches without re-hitting the network. For each existing
`wiki:`-coded tournament it deletes the tournament's matches and re-ingests
them from the cached article with the current parser — so mis-keyed corrupt
rows (which carry a different source_key than the corrected match) can't
linger. Reuses scrape_wiki's own ingest paths so nothing diverges.

    python manage.py resweep_wiki            # all wiki tournaments
    python manage.py resweep_wiki --limit 5  # smoke test on a few
    python manage.py resweep_wiki --dry-run  # report the plan, change nothing

Run `rate --rebuild` + the build_* commands afterwards so ratings and derived
tables reflect the corrected results.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.ingest.models import Match, Player, Tournament
from apps.ingest.wiki_client import WikiClient

from .scrape_wiki import Allocator, Command as WikiScrape

CUP_HINTS = (("thomas cup", "thomas"), ("uber cup", "uber"),
             ("sudirman cup", "sudirman"))


class Command(BaseCommand):
    help = "Re-ingest all cached Wikipedia tournaments with the current parser."

    def add_arguments(self, p):
        p.add_argument("--limit", type=int, default=0,
                       help="only process the first N tournaments (smoke test)")
        p.add_argument("--dry-run", action="store_true",
                       help="report what would happen; make no changes")

    def handle(self, *a, **o):
        # Wait for the row lock instead of erroring if a collector is mid-write.
        with connection.cursor() as c:
            c.execute("PRAGMA busy_timeout=60000")

        scrape = WikiScrape()
        scrape.stdout = self.stdout
        client = WikiClient()
        players = Allocator(Player)
        tourns = Allocator(Tournament)
        matches = Allocator(Match)

        qs = Tournament.objects.filter(code__startswith="wiki:").order_by("start_date")
        if o["limit"]:
            qs = qs[: o["limit"]]
        wiki_tourns = list(qs)
        self.stdout.write(f"re-ingesting {len(wiki_tourns)} wiki tournaments…")

        done = failed = total_before = total_after = 0
        for t in wiki_tourns:
            title = t.code[len("wiki:"):]
            tier = t.category_name or ""
            name_l = (t.name or "").lower()
            before = Match.objects.filter(tournament=t).count()
            total_before += before
            if o["dry_run"]:
                self.stdout.write(f"  · {title[:55]:55} matches={before}")
                continue
            try:
                with transaction.atomic():
                    Match.objects.filter(tournament=t).delete()
                    cup = next((c for h, c in CUP_HINTS if h in name_l), None)
                    if cup:
                        n = scrape._one_team(client, title, cup, False,
                                             players, tourns, matches)
                    elif title.startswith("Badminton at the"):
                        n = scrape._one(client, title, tier, False,
                                        players, tourns, matches, team=True)
                    else:
                        n = scrape._one(client, title, tier, False,
                                        players, tourns, matches)
            except Exception as e:  # noqa: BLE001 - one bad article mustn't stop the sweep
                failed += 1
                self.stderr.write(f"  ! {title}: {e}")
                continue
            after = Match.objects.filter(tournament=t).count()
            total_after += after
            done += 1
            flag = "" if after else "  (no matches parsed!)"
            self.stdout.write(f"  ✓ {title[:50]:50} {before:3} -> {after:3}{flag}")

        client.close()
        self.stdout.write(self.style.SUCCESS(
            f"done: {done} re-ingested, {failed} failed; "
            f"matches {total_before} -> {total_after}"))
