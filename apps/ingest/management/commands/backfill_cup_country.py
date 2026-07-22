"""Backfill missing player country_code from team-cup tie context.

Some wiki players have no country_code (their nation appeared as a full name the
parser didn't map). In a team cup each rubber side represents one of the tie's
two nations, so we can recover a missing player's country from the tie: group a
round's rubbers into ties (at most two nations each), then assign each side its
nation — the known one, or the tie's other nation when this side is unknown.
Only fills empty country_codes; never overwrites. Country doesn't affect ratings,
so no re-rate is needed after.

    python manage.py backfill_cup_country            # apply
    python manage.py backfill_cup_country --dry-run  # report only
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from apps.ingest.models import Match, Player

from .fix_cup_events import team_cup_tournaments


def _side_country(players):
    c = Counter(p.country_code for p in players if p.country_code)
    return c.most_common(1)[0][0] if c else None


class Command(BaseCommand):
    help = "Fill missing player country_code from team-cup ties."

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true")

    def handle(self, *a, **o):
        tour_ids = list(team_cup_tournaments().values_list("tournament_id", flat=True))
        self.stdout.write(f"{len(tour_ids)} team-cup tournaments")
        fills: dict = {}  # player_id -> country_code
        for tid in tour_ids:
            ms = list(
                Match.objects.filter(tournament_id=tid)
                .prefetch_related("lineup__player")
                .order_by("round_order", "match_id")
            )
            # Group consecutive rubbers into ties (<= two nations each).
            raw = []
            for m in ms:
                s1 = [l.player for l in m.lineup.all() if l.side == 1]
                s2 = [l.player for l in m.lineup.all() if l.side == 2]
                c1, c2 = _side_country(s1), _side_country(s2)
                known = {c for c in (c1, c2) if c}
                cur = raw[-1] if raw else None
                if cur is not None and len(cur["countries"] | known) <= 2:
                    cur["countries"] |= known
                else:
                    cur = {"countries": set(known), "rubbers": []}
                    raw.append(cur)
                cur["rubbers"].append((s1, s2, c1, c2))

            for rt in raw:
                cs = rt["countries"]
                if len(cs) != 2:
                    continue  # can't disambiguate a one-nation (or empty) tie
                for s1, s2, c1, c2 in rt["rubbers"]:
                    sc1 = c1 or next((c for c in cs if c != c2), None)
                    sc2 = c2 or next((c for c in cs if c != c1), None)
                    for players, sc in ((s1, sc1), (s2, sc2)):
                        if not sc:
                            continue
                        for pl in players:
                            if not pl.country_code and fills.get(pl.player_id, sc) == sc:
                                fills[pl.player_id] = sc

        if o["dry_run"]:
            by_cc = Counter(fills.values())
            self.stdout.write(f"would fill {len(fills)} players: {dict(by_cc)}")
            return

        players = list(Player.objects.filter(player_id__in=fills))
        for pl in players:
            pl.country_code = fills[pl.player_id]
        Player.objects.bulk_update(players, ["country_code"], batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"filled {len(players)} player countries"))
