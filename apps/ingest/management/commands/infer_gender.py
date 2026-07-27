"""`manage.py infer_gender` — tag players M/F from discipline participation.

Gender is NOT in the payload and is never guessed from names. But a player who
appears in MS or MD is male, and WS or WD is female — an unambiguous signal from
the discipline itself (PRD keeps ratings keyed by discipline, not sex; this is
only to split the XD board and label pairs).

An XD-ONLY player (never in a gendered singles/doubles event) still resolves:
in mixed doubles each SIDE is one man + one woman, so a player is the opposite
gender of their XD partner. We propagate the discipline-derived genders across
XD partnerships to a fixpoint, catching players who only ever played mixed.
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.ingest.models import MatchPlayer, Player

# Any singles/doubles event of that gender, including masters (MS45) and youth
# (MSU19) suffixes — match on the prefix so those aren't left blank.
MALE_Q = Q(match__event__startswith="MS") | Q(match__event__startswith="MD")
FEMALE_Q = Q(match__event__startswith="WS") | Q(match__event__startswith="WD")


def _xd_partner_pairs() -> set[frozenset]:
    """Every unordered player pair that partnered on one side of an XD rubber."""
    sides: dict = defaultdict(lambda: defaultdict(list))  # match -> side -> [pid]
    for mp in MatchPlayer.objects.filter(match__event="XD").values(
        "match_id", "side", "player_id"
    ):
        sides[mp["match_id"]][mp["side"]].append(mp["player_id"])
    pairs = set()
    for by_side in sides.values():
        for players in by_side.values():
            if len(players) == 2:
                pairs.add(frozenset(players))
    return pairs


class Command(BaseCommand):
    help = "Infer player gender (M/F) from discipline + XD-partner propagation."

    def handle(self, *args, **opts):
        males = set(
            MatchPlayer.objects.filter(MALE_Q)
            .values_list("player_id", flat=True)
            .distinct()
        )
        females = set(
            MatchPlayer.objects.filter(FEMALE_Q)
            .values_list("player_id", flat=True)
            .distinct()
        )
        # A handful of ids may appear in both (data noise); trust the majority
        # discipline by leaving conflicts blank.
        conflict = males & females
        males -= conflict
        females -= conflict

        gender: dict[int, str] = {p: "M" for p in males}
        gender.update({p: "F" for p in females})

        # Fixpoint propagation over XD partnerships: partner = opposite gender.
        pairs = _xd_partner_pairs()
        n_prop = 0
        changed = True
        while changed:
            changed = False
            for pair in pairs:
                a, b = tuple(pair)
                ga, gb = gender.get(a), gender.get(b)
                if ga and not gb:
                    gender[b] = "F" if ga == "M" else "M"
                    n_prop += 1
                    changed = True
                elif gb and not ga:
                    gender[a] = "F" if gb == "M" else "M"
                    n_prop += 1
                    changed = True

        males = {p for p, g in gender.items() if g == "M"}
        females = {p for p, g in gender.items() if g == "F"}

        n_m = Player.objects.filter(player_id__in=males).update(gender="M")
        n_f = Player.objects.filter(player_id__in=females).update(gender="F")
        n_blank = Player.objects.exclude(
            player_id__in=males | females
        ).update(gender="")
        self.stdout.write(
            self.style.SUCCESS(
                f"gender: {n_m} male, {n_f} female, {n_blank} blank "
                f"(+{n_prop} resolved via XD partners)."
            )
        )
