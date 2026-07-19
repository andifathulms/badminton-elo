"""Backfill 1983-2006 tournaments from Wikipedia (the [[wikipedia-gap-source]]).

Fetches each tournament article's wikitext (cache-first, polite), parses the
draw brackets + finals table (apps.ingest.wiki_parse), and ingests plain
Match/Game/MatchPlayer/Player rows under a synthetic id namespace. Players are
keyed by their stable [[wiki title]]; reconcile to real BWF ids later by name.

    python manage.py scrape_wiki --series all-england --from 1983 --to 2006
    python manage.py scrape_wiki --pages "1992 All England Open Badminton Championships"
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_date

from apps.ingest.models import Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.wiki_client import WikiClient
from apps.ingest import wiki_parse

BASE = 2_000_000_000  # synthetic id namespace (real BWF ids are < 100000)

ROUND_CODE = {
    "Round of 128": ("R128", 1), "Round of 64": ("R64", 2),
    "Round of 32": ("R32", 3), "Round of 16": ("R16", 4),
    "Quarter-finals": ("QF", 5), "Semi-finals": ("SF", 6), "Final": ("F", 7),
}

# Well-known series -> (article suffix, tier label). Article title is
# "{year} {suffix}"; misses (no such page) are skipped.
SERIES = {
    "all-england": ("All England Open Badminton Championships", "All England"),
    "world-championships": ("BWF World Championships", "World Championships"),
    "indonesia-open": ("Indonesia Open (badminton)", "Grand Prix"),
    "malaysia-open": ("Malaysia Open (badminton)", "Grand Prix"),
    "china-open": ("China Open (badminton)", "Grand Prix"),
    "japan-open": ("Japan Open (badminton)", "Grand Prix"),
    "denmark-open": ("Denmark Open", "Grand Prix"),
    "thomas-cup": ("Thomas Cup", "Thomas Cup"),
    "uber-cup": ("Uber Cup", "Uber Cup"),
    "sudirman-cup": ("Sudirman Cup", "Sudirman Cup"),
}


class Allocator:
    """Hands out stable synthetic ids per table, continuing past existing rows."""
    def __init__(self, model, field="pk"):
        from django.db.models import Max
        cur = model.objects.filter(**{f"{field}__gte": BASE}).aggregate(m=Max(field))["m"]
        self.n = cur or (BASE - 1)

    def next(self):
        self.n += 1
        return self.n


def clean_name(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def infobox_meta(text: str) -> dict:
    """Pull tournament name + dates from the {{infobox badminton event}}."""
    meta = {"name": None, "start": None, "end": None}
    m = re.search(r"\|\s*name\s*=\s*(.+)", text)
    if m:
        nm = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", m.group(1)).strip()
        meta["name"] = re.sub(r"'''|\{\{[^}]*\}\}", "", nm).strip() or None
    dates = re.findall(r"\{\{(?:Start|End) date\|(\d{4})\|(\d{1,2})\|(\d{1,2})", text)
    if dates:
        y, mo, d = dates[0]
        meta["start"] = parse_date(f"{y}-{int(mo):02d}-{int(d):02d}")
        y2, mo2, d2 = dates[-1]
        meta["end"] = parse_date(f"{y2}-{int(mo2):02d}-{int(d2):02d}")
    return meta


def scoring_format(games) -> str:
    mx = max((max(a, b) for a, b in games), default=15)
    target = 21 if mx > 15 else (15 if mx > 11 else 11)
    return f"3x{target}"


class Command(BaseCommand):
    help = "Ingest 1983-2006 tournaments from Wikipedia into the synthetic namespace."

    def add_arguments(self, p):
        p.add_argument("--series", choices=sorted(SERIES))
        p.add_argument("--from", type=int, dest="yr_from", default=1983)
        p.add_argument("--to", type=int, dest="yr_to", default=2006)
        p.add_argument("--pages", help="explicit article titles, ;-separated")
        p.add_argument("--tier", default="", help="category_name for --pages")
        p.add_argument("--refresh", action="store_true", help="ignore cache")

    def handle(self, *a, **o):
        if o["pages"]:
            jobs = [(t.strip(), o["tier"]) for t in o["pages"].split(";") if t.strip()]
        elif o["series"]:
            suffix, tier = SERIES[o["series"]]
            jobs = [(f"{y} {suffix}", tier) for y in range(o["yr_from"], o["yr_to"] + 1)]
        else:
            self.stderr.write("give --series or --pages"); return

        client = WikiClient()
        players = Allocator(Player)
        tourns = Allocator(Tournament)
        matches = Allocator(Match)
        tot_t = tot_m = 0
        try:
            for title, tier in jobs:
                if o["refresh"]:
                    cp = client._cache_path(title)
                    if cp.exists():
                        cp.unlink()
                wt = client.wikitext(title)
                if not wt:
                    self.stdout.write(f"  · {title}: no article, skip")
                    continue
                parsed = wiki_parse.parse_article(wt)
                if not parsed:
                    self.stdout.write(f"  · {title}: no matches parsed, skip")
                    continue
                n = self._ingest(title, tier, wt, parsed, players, tourns, matches)
                tot_t += 1; tot_m += n
                self.stdout.write(self.style.SUCCESS(f"  ✓ {title}: {n} matches"))
        finally:
            client.close()
        self.stdout.write(self.style.SUCCESS(f"Done: {tot_t} tournaments, {tot_m} matches."))

    @transaction.atomic
    def _ingest(self, title, tier, wt, parsed, players, tourns, matches):
        meta = infobox_meta(wt)
        code = f"wiki:{title}"
        t = Tournament.objects.filter(code=code).first()
        if not t:
            t = Tournament(tournament_id=tourns.next(), code=code)
        t.name = meta["name"] or clean_name(title)
        t.start_date = meta["start"]
        t.end_date = meta["end"]
        t.category_name = tier
        t.save()

        def get_player(team_player, country):
            wtitle, disp = team_player
            p = Player.objects.filter(wiki_title=wtitle).first()
            if not p:
                p = Player(player_id=players.next(), wiki_title=wtitle)
            p.name_display = clean_name(wtitle) or disp
            if country and not p.country_code:
                p.country_code = country
            p.save()
            return p

        n = 0
        for m in parsed:
            rname, rorder = ROUND_CODE.get(m["round_label"], ("", 0))
            skey = "wiki:{}:{}:{}:{}|{}".format(
                title, m["event"], m["round_index"],
                "+".join(sorted(p[0] for p in m["side1"]["players"])),
                "+".join(sorted(p[0] for p in m["side2"]["players"])))
            match = Match.objects.filter(source_key=skey).first()
            if not match:
                match = Match(match_id=matches.next(), source_key=skey)
            match.tournament = t
            match.event = m["event"]
            match.round_name = rname
            match.round_order = rorder
            match.match_time_utc = None
            match.score_status = "Retired" if m["retired"] else "Normal"
            match.winner_side = m["winner_side"]
            match.scoring_format = scoring_format(m["games"]) if m["games"] else ""
            match.rating_excluded = not m["games"]  # finals-only rows w/o scores
            match.save()
            match.games.all().delete()
            match.lineup.all().delete()
            for gi, (s1, s2) in enumerate(m["games"], 1):
                Game.objects.create(match=match, game_no=gi, side1_points=s1, side2_points=s2)
            for side, team in ((1, m["side1"]), (2, m["side2"])):
                for tp in team["players"]:
                    p = get_player(tp, team["country"])
                    MatchPlayer.objects.get_or_create(match=match, side=side, player=p)
            n += 1
        return n
