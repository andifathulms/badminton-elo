"""`manage.py purge_byes` — delete bye pseudo-matches and "Bye" players.

Older Wikipedia ingests stored some byes as a player named e.g.
"[[Bye (sports)|Bye]]" or "bye bye", so a walk-through became a rated "win".
The parser now skips them (wiki_parse.is_bye); this removes what's stored.
Dry-run by default; --apply to delete. Run `rate` afterwards.
"""
from __future__ import annotations

from django.db import transaction

from apps.ingest.management.base import DataCommand
from apps.ingest.models import Match, Player
from apps.ingest.wiki_parse import is_bye


class Command(DataCommand):
    help = "Delete bye pseudo-matches and bye placeholder players."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        byes = [p for p in Player.objects.filter(name_display__icontains="bye")
                if is_bye(p.name_display)]
        matches = Match.objects.filter(lineup__player__in=byes).distinct()
        self.stdout.write(f"{len(byes)} bye players in {matches.count()} matches: "
                          + ", ".join(repr(p.name_display) for p in byes))
        if not opts["apply"]:
            self.stdout.write("dry run — pass --apply to delete.")
            return
        with transaction.atomic():
            Match.objects.filter(match_id__in=list(matches.values_list("match_id", flat=True))).delete()
            Player.objects.filter(pk__in=[p.pk for p in byes]).delete()
        self.stdout.write(self.style.SUCCESS("purged."))
