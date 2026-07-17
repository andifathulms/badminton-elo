"""`manage.py infer_gender` — tag players M/F from discipline participation.

Gender is NOT in the payload and is never guessed from names. But a player who
appears in MS or MD is male, and WS or WD is female — an unambiguous signal from
the discipline itself (PRD keeps ratings keyed by discipline, not sex; this is
only to split the XD board and label pairs). XD-only players stay blank.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ingest.models import MatchPlayer, Player

MALE_EVENTS = ("MS", "MD")
FEMALE_EVENTS = ("WS", "WD")


class Command(BaseCommand):
    help = "Infer player gender (M/F) from MS/MD vs WS/WD participation."

    def handle(self, *args, **opts):
        males = set(
            MatchPlayer.objects.filter(match__event__in=MALE_EVENTS)
            .values_list("player_id", flat=True)
            .distinct()
        )
        females = set(
            MatchPlayer.objects.filter(match__event__in=FEMALE_EVENTS)
            .values_list("player_id", flat=True)
            .distinct()
        )
        # A handful of ids may appear in both (data noise); trust the majority
        # discipline by leaving conflicts blank.
        conflict = males & females
        males -= conflict
        females -= conflict

        n_m = Player.objects.filter(player_id__in=males).update(gender="M")
        n_f = Player.objects.filter(player_id__in=females).update(gender="F")
        Player.objects.filter(player_id__in=conflict).update(gender="")
        self.stdout.write(
            self.style.SUCCESS(
                f"gender: {n_m} male, {n_f} female, {len(conflict)} ambiguous (blank)."
            )
        )
