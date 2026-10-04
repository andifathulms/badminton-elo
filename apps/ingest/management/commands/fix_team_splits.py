"""`manage.py fix_team_splits` — put each rubber in the right gendered team event.

scrape_bwf_team splits a men's-and-women's team event into '…:M' and '…:W'
tournaments by draw label. Labels it couldn't read ('Uber Cup - Group A',
'2018 EWTC') put women's rubbers in the men's tournament. Their disciplines
are re-derived from the lineup (fix_cup_events), so a WS/WD rubber in a men's
split — or MS/MD in a women's — is moved to its sibling (created if missing).
Run after fix_cup_events. Dry run by default; --apply to move.
"""
from __future__ import annotations

from collections import Counter

from django.db import transaction

from apps.ingest.management.base import DataCommand
from apps.ingest.management.commands.scrape_bwf_team import _gendered_name
from apps.ingest.models import Match, Tournament
from apps.ingest.normalize import synthetic_tournament_id

WRONG = {"M": ("WS", "WD"), "W": ("MS", "MD")}


def sibling_name(name: str, gender: str) -> str:
    """The other gender's name: swap an embedded Men's/Women's, else re-tag."""
    src, dst = ("Men's", "Women's") if gender == "W" else ("Women's", "Men's")
    if src in name and not (gender == "W" and "Women's" in name):
        return name.replace(src, dst, 1)
    base = name
    for tag in (" – Men's team", " – Women's team"):
        base = base.replace(tag, "")
    return _gendered_name(base, gender)


class Command(DataCommand):
    help = "Move rubbers stored in the wrong gendered team tournament."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def _sibling(self, t, gender):
        guid = t.code.rsplit(":", 1)[0]
        code = f"{guid}:{gender}"
        sib = Tournament.objects.filter(code=code).first()
        if sib:
            return sib
        return Tournament.objects.create(
            tournament_id=synthetic_tournament_id(code), code=code,
            name=sibling_name(t.name, gender),
            category_name=t.category_name, start_date=t.start_date,
            end_date=t.end_date, logo_url=t.logo_url,
        )

    def handle(self, *args, **opts):
        moves = Counter()
        plan = []
        for t in Tournament.objects.filter(code__regex=r":(M|W)$"):
            gender = t.code[-1]
            wrong = list(Match.objects.filter(tournament=t, event__in=WRONG[gender])
                         .values_list("match_id", flat=True))
            if wrong:
                plan.append((t, "W" if gender == "M" else "M", wrong))
                moves[f"{t.name[:50]} -> {'women' if gender == 'M' else 'men'}"] += len(wrong)
        for k, n in moves.most_common():
            self.stdout.write(f"  {n:4d}  {k}")
        self.stdout.write(f"{sum(moves.values())} rubbers in {len(plan)} tournaments")
        if not opts["apply"]:
            self.stdout.write("dry run — pass --apply to move.")
            return
        with transaction.atomic():
            for t, gender, ids in plan:
                sib = self._sibling(t, gender)
                Match.objects.filter(match_id__in=ids).update(tournament=sib, draw=None)
        self.stdout.write(self.style.SUCCESS("moved."))
