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

import math

ORDINAL_ROUND = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
# rounds-from-final -> (code, chronological order)
STD_BY_DISTANCE = {
    0: ("F", 90), 1: ("SF", 80), 2: ("QF", 70), 3: ("R16", 40),
    4: ("R32", 30), 5: ("R64", 20), 6: ("R128", 10),
}


def normalize_round(label: str, round_index: int, bracket_size: int = 0) -> tuple[str, int]:
    """Map any Wikipedia round label -> (display code, chronological order).

    Handles 'Round of 32', 'Quarterfinals'/'Quarter-finals', 'First round',
    'Semifinals', 'Final', etc. Order is monotonic with progression so the
    rating engine processes earlier rounds first within a tournament."""
    l = re.sub(r"[-\s]+", " ", label.lower()).strip()
    if "final" in l and "semi" not in l and "quarter" not in l:
        return ("F", 90)
    if "semi" in l:
        return ("SF", 80)
    if "quarter" in l:
        return ("QF", 70)
    m = re.search(r"round of (\d+)", l)
    if m:
        n = int(m.group(1))
        code = {128: "R128", 64: "R64", 32: "R32", 16: "R16"}.get(n, f"R{n}")
        order = {128: 10, 64: 20, 32: 30, 16: 40}.get(n, 25)
        return (code, order)
    for word, i in ORDINAL_ROUND.items():
        if l.startswith(word + " round") or l == word:
            return (f"R{i}", 10 + i * 8)
    m = re.search(r"round (\d+)", l)  # "Round 1", "Round 2"…
    if m:
        i = int(m.group(1))
        return (f"R{i}", 10 + i * 8)
    # generic/unlabeled (e.g. "RD3"): infer from bracket geometry
    if bracket_size >= 2:
        dist = int(round(math.log2(bracket_size))) - round_index
        if dist in STD_BY_DISTANCE:
            return STD_BY_DISTANCE[dist]
    return (label[:14], 10 + round_index)

# Wikipedia category -> tier label. We enumerate year-prefixed members of each
# category (robust to sponsor renames and missing years, unlike title guessing).
CATEGORIES = {
    "All England Open Badminton Championships": "All England",
    "BWF World Championships": "World Championships",
    "Denmark Open": "Grand Prix",
    "Indonesia Open (badminton)": "Grand Prix",
    "Malaysia Open (badminton)": "Grand Prix",
    "China Open (badminton)": "Grand Prix",
    "Japan Open (badminton)": "Grand Prix",
    "Korea Open (badminton)": "Grand Prix",
    "Singapore Open (badminton)": "Grand Prix",
    "Thailand Open (badminton)": "Grand Prix",
    "Hong Kong Open (badminton)": "Grand Prix",
    "Swiss Open (badminton)": "Grand Prix",
    "German Open (badminton)": "Grand Prix",
    "French Open (badminton)": "Grand Prix",
    "Chinese Taipei Open": "Grand Prix",
    "India Open (badminton)": "Grand Prix",
    "US Open (badminton)": "Grand Prix",
    "Scandinavian Open Badminton Championships": "Grand Prix",
    "Dutch Open (badminton)": "Grand Prix",
    "Canada Open (badminton)": "Grand Prix",
}
YEAR_RE = re.compile(r"^(19|20)(\d{2})\b")

DISCIPLINES = [
    ("Men's singles", "MS"), ("Women's singles", "WS"), ("Men's doubles", "MD"),
    ("Women's doubles", "WD"), ("Mixed doubles", "XD"),
]


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
        p.add_argument("--from", type=int, dest="yr_from", default=1983)
        p.add_argument("--to", type=int, dest="yr_to", default=2006)
        p.add_argument("--pages", help="explicit article titles, ;-separated")
        p.add_argument("--category", help="one Wikipedia category to enumerate")
        p.add_argument("--all-majors", action="store_true",
                       help="enumerate every preset major-event category")
        p.add_argument("--tier", default="", help="category_name for --pages")
        p.add_argument("--refresh", action="store_true", help="ignore cache")

    def handle(self, *a, **o):
        client = WikiClient()
        yf, yt = o["yr_from"], o["yr_to"]

        def in_range(title):
            m = YEAR_RE.match(title)
            return bool(m) and yf <= int(m.group(0)) <= yt

        if o["pages"]:
            jobs = [(t.strip(), o["tier"]) for t in o["pages"].split(";") if t.strip()]
        elif o["category"] or o["all_majors"]:
            cats = ({o["category"]: o["tier"]} if o["category"] else CATEGORIES)
            jobs = []
            for cat, tier in cats.items():
                members = [t for t in client.category_members(cat) if in_range(t)]
                self.stdout.write(f"[{cat}] {len(members)} editions in {yf}-{yt}")
                jobs += [(t, tier) for t in members]
        else:
            self.stderr.write("give --pages, --category, or --all-majors"); return

        players = Allocator(Player)
        tourns = Allocator(Tournament)
        matches = Allocator(Match)
        tot_t = tot_m = 0
        try:
            for title, tier in jobs:
                try:
                    n = self._one(client, title, tier, o["refresh"],
                                  players, tourns, matches)
                except Exception as e:  # never let one bad article kill the sweep
                    self.stdout.write(self.style.WARNING(f"  ! {title}: {e}"))
                    continue
                if n is None:
                    continue
                tot_t += 1; tot_m += n
                self.stdout.write(self.style.SUCCESS(f"  ✓ {title}: {n} matches"))
        finally:
            client.close()
        self.stdout.write(self.style.SUCCESS(f"Done: {tot_t} tournaments, {tot_m} matches."))

    def _one(self, client, title, tier, refresh, players, tourns, matches):
        """Fetch + parse + ingest one tournament. Returns match count or None."""
        if refresh:
            cp = client._cache_path(title)
            if cp.exists():
                cp.unlink()
        wt = client.wikitext(title)
        if not wt:
            return None
        parsed = wiki_parse.parse_article(wt)
        # Big events (World Champs, modern Opens) keep full draws in per-discipline
        # sub-articles ("{title} – Men's singles"); pull them when the main
        # article carries no bracket rounds of its own.
        if not any(m["round_index"] < 90 for m in parsed):
            parsed = wiki_parse.dedupe(parsed + self._subarticles(client, title))
        if not parsed:
            return None
        return self._ingest(title, tier, wt, parsed, players, tourns, matches)

    def _subarticles(self, client, title):
        """Fetch + parse the 5 per-discipline sub-articles, if they exist."""
        out = []
        for disc, ev in DISCIPLINES:
            for sep in ("–", "-"):  # en-dash first, then hyphen
                swt = client.wikitext(f"{title} {sep} {disc}")
                if swt:
                    out += wiki_parse.parse_bracket(swt, ev)
                    break
        return out

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
            rname, rorder = normalize_round(
                m["round_label"], m["round_index"], m["bracket_size"])
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
