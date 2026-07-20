"""Remove duplicate team-cup tournaments.

The BWF calendar lists e.g. "TotalEnergies BWF Sudirman Cup Finals 2025" (real
id, a logo, but 0 matches) while the rubber data lives under the Wikipedia
tournament "2025 Sudirman Cup" (synthetic id, 146 matches). This copies the BWF
logo onto the matching Wikipedia cup(s) and deletes the empty BWF duplicate.
Thomas & Uber combined calendar entries map to BOTH the Thomas and Uber cups.
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.ingest.models import Tournament

BASE = 2_000_000_000
CUP_KW = {"Thomas Cup": "Thomas Cup", "Uber Cup": "Uber Cup",
          "Sudirman Cup": "Sudirman Cup"}


class Command(BaseCommand):
    help = "Merge BWF-calendar cup duplicates into the Wikipedia cups."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        removed = logos = 0
        for t in (Tournament.objects.filter(tournament_id__lt=BASE)
                  .annotate(mc=Count("matches")).filter(mc=0)):
            ym = re.search(r"(19|20)\d{2}", t.name)
            if not ym:
                continue
            year = ym.group(0)
            cups = [kw for kw in CUP_KW if kw in t.name]
            if not cups:
                continue
            matched_any = False
            for cup in cups:
                wiki = Tournament.objects.filter(code=f"wiki:{year} {cup}").first()
                if not wiki:
                    continue
                matched_any = True
                if t.logo_url and not wiki.logo_url:
                    self.stdout.write(f"  logo -> {wiki.name}")
                    if o["apply"]:
                        wiki.logo_url = t.logo_url; wiki.save(update_fields=["logo_url"])
                    logos += 1
            if matched_any:
                self.stdout.write(f"  drop duplicate: {t.name} (#{t.tournament_id}, 0 matches)")
                if o["apply"]:
                    t.delete()
                removed += 1
        verb = "Removed" if o["apply"] else "Would remove"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {removed} duplicate cup tournaments; copied {logos} logos."
            + ("" if o["apply"] else "  (dry-run; pass --apply)")))
