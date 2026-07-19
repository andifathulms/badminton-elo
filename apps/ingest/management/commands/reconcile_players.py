"""Reconcile Wikipedia-sourced players (synthetic ids) with BWF players.

Wikipedia backfill ([[wikipedia-gap-source]]) creates players under a synthetic
id namespace keyed by [[wiki title]]; BWF players are keyed by real id. A
long-career player (Lee Chong Wei, Lin Dan) then exists twice. This command
matches them by normalised name (+ country when known) and, for UNAMBIGUOUS
matches only, merges the Wikipedia record into the BWF one:

  * repoint the Wiki player's lineup rows onto the BWF player
  * copy wiki_title onto the BWF player so future scrapes land there
  * fill the BWF player's country from Wikipedia if it was blank
  * delete the now-empty Wiki duplicate

Dry-run by default. Re-rate after --apply so ratings reflect the merges.

    python manage.py reconcile_players            # report only
    python manage.py reconcile_players --apply     # perform safe merges
    python manage.py reconcile_players --apply --name-only   # also merge when
        # Wiki country is blank but the name is a unique BWF match
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import MatchPlayer, Player

BASE = 2_000_000_000

# ISO-3166 (Wikipedia flags) -> IOC/BWF country codes, for the mismatches only.
COUNTRY_CANON = {
    "IDN": "INA", "MYS": "MAS", "VNM": "VIE", "DEU": "GER", "NLD": "NED",
    "CHE": "SUI", "DNK": "DEN", "BGR": "BUL", "PRT": "POR", "TWN": "TPE",
    "LKA": "SRI", "MMR": "MYA", "KOR": "KOR", "GRC": "GRE", "SVK": "SVK",
    "HRV": "CRO", "SVN": "SLO", "PHL": "PHI", "MNG": "MGL",
}


def canon_country(c: str) -> str:
    c = (c or "").upper()
    return COUNTRY_CANON.get(c, c)


def norm(name: str) -> str:
    """Case/accent/markup-insensitive, word-order-insensitive key.
    'LEE Chong Wei' and \"'''Lee Chong Wei'''\" -> 'chong lee wei'."""
    name = re.sub(r"'{2,}|<[^>]+>", " ", name)  # strip bold + <br/> artifacts
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(sorted(re.sub(r"[^a-z ]", " ", s.lower()).split()))


class Command(BaseCommand):
    help = "Merge Wikipedia player duplicates into their BWF counterparts."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="perform merges")
        p.add_argument("--name-only", action="store_true",
                       help="also merge when Wiki country is blank (name unique)")
        p.add_argument("--show", type=int, default=15, help="examples to print")

    def handle(self, *a, **o):
        # index BWF players by normalised name
        bwf_by_name = defaultdict(list)
        for p in Player.objects.filter(player_id__lt=BASE):
            bwf_by_name[norm(p.name_display)].append(p)

        auto, ambiguous, unmatched = [], [], []
        for w in Player.objects.filter(player_id__gte=BASE).exclude(wiki_title=""):
            cands = bwf_by_name.get(norm(w.name_display), [])
            if not cands:
                unmatched.append(w); continue
            if w.country_code:
                wc = canon_country(w.country_code)
                cc = [c for c in cands if canon_country(c.country_code) == wc]
                # name unique in BWF but country differs -> still confident it's
                # the same person (country codes are noisy); treat as auto.
                if not cc and len(cands) == 1:
                    cc = cands
            else:
                cc = cands if o["name_only"] else []
                if not cc:
                    unmatched.append(w); continue
            if len(cc) == 1:
                auto.append((w, cc[0]))
            else:
                ambiguous.append((w, cc))

        self.stdout.write(self.style.SUCCESS(
            f"auto-mergeable: {len(auto)}  |  ambiguous: {len(ambiguous)}  |  "
            f"unmatched (kept as-is): {len(unmatched)}"))
        self.stdout.write("\n— sample auto-merges (Wiki -> BWF) —")
        for w, b in auto[:o["show"]]:
            self.stdout.write(f"   {w.name_display} [{w.country_code or '?'}] "
                              f"#{w.player_id} -> {b.name_display} #{b.player_id}")
        if ambiguous:
            self.stdout.write("\n— AMBIGUOUS (needs your eye) —")
            for w, cs in ambiguous[:o["show"]]:
                opts = ", ".join(f"{c.name_display}#{c.player_id}[{c.country_code}]" for c in cs)
                self.stdout.write(f"   {w.name_display}[{w.country_code}] -> {opts}")
        if unmatched[:o["show"]]:
            self.stdout.write("\n— unmatched sample (Wikipedia-only players) —")
            for w in unmatched[:o["show"]]:
                self.stdout.write(f"   {w.name_display} [{w.country_code or '?'}]")

        if not o["apply"]:
            self.stdout.write(self.style.WARNING(
                "\nDry-run. Re-run with --apply to merge the auto-mergeable set."))
            return

        merged = 0
        for w, b in auto:
            self._merge(w, b); merged += 1
        # tidy leftover markup in the remaining Wikipedia-only players' names
        cleaned = 0
        for p in Player.objects.filter(player_id__gte=BASE):
            fixed = re.sub(r"\s+", " ", re.sub(r"'{2,}|<[^>]+>", " ", p.name_display)).strip()
            if fixed and fixed != p.name_display:
                p.name_display = fixed; p.save(update_fields=["name_display"]); cleaned += 1
        self.stdout.write(self.style.SUCCESS(
            f"\nMerged {merged} duplicates; cleaned {cleaned} names. "
            f"Run `manage.py rate --rebuild` next."))

    @transaction.atomic
    def _merge(self, wiki_p: Player, bwf_p: Player):
        for mp in MatchPlayer.objects.filter(player=wiki_p):
            if MatchPlayer.objects.filter(
                    match=mp.match, side=mp.side, player=bwf_p).exists():
                mp.delete()  # already present (shouldn't happen) — drop the dup
            else:
                mp.player = bwf_p
                mp.save()
        changed = False
        if not bwf_p.wiki_title:
            bwf_p.wiki_title = wiki_p.wiki_title; changed = True
        if not bwf_p.country_code and wiki_p.country_code:
            bwf_p.country_code = wiki_p.country_code; changed = True
        if changed:
            bwf_p.save()
        wiki_p.delete()
