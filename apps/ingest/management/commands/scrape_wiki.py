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
from datetime import datetime, time as dt_time, timedelta, timezone as dt_tz

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

# Team-cup category -> rubber discipline mapping key (see wiki_parse.CUP_EVENT).
CUPS = {"Thomas Cup": "thomas", "Uber Cup": "uber", "Sudirman Cup": "sudirman"}

# Multi-sport events: category -> tier. Articles are "Badminton at the {year}
# {Games}" with individual events (inline brackets or "– Men's singles"
# sub-articles) and sometimes team events ("– Men's team"). Not in BWF's data
# at any year, so pull every edition.
GAMES = {
    "Badminton at the Summer Olympics": "Olympics",
    "Badminton at the Asian Games": "Asian Games",
    "Badminton at the Commonwealth Games": "Commonwealth Games",
    "Badminton at the European Games": "European Games",
    "Badminton at the Pan American Games": "Pan American Games",
    "Badminton at the African Games": "African Games",
}
# SEA Games badminton has no clean category; construct titles for its editions.
SEA_YEARS = list(range(1977, 2007, 2)) + [1959, 1961, 1965, 1967, 1969, 1971, 1973]
TEAM_SUBS = [("Men's team", "thomas"), ("Women's team", "uber"),
             ("Mixed team", "sudirman")]


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
        p.add_argument("--cups", action="store_true",
                       help="ingest Thomas/Uber/Sudirman team cups (rubber-level)")
        p.add_argument("--games", action="store_true",
                       help="ingest multi-sport events (Olympics, Asian/SEA/etc.)")
        p.add_argument("--tier", default="", help="category_name for --pages")
        p.add_argument("--refresh", action="store_true", help="ignore cache")

    def handle(self, *a, **o):
        client = WikiClient()
        yf, yt = o["yr_from"], o["yr_to"]

        def in_range(title):
            m = YEAR_RE.match(title)
            return bool(m) and yf <= int(m.group(0)) <= yt

        players = Allocator(Player)
        tourns = Allocator(Tournament)
        matches = Allocator(Match)
        tot_t = tot_m = 0

        if o["cups"]:
            # Thomas/Uber years live in "Thomas & Uber Cup" (often combined
            # articles); Sudirman in its own category. Ingest Thomas and Uber as
            # separate tournaments so men's/women's rubbers aren't mixed.
            tu, sud = set(), set()
            for t in client.category_members("Thomas & Uber Cup"):
                mm = YEAR_RE.match(t)
                if mm and in_range(t):
                    tu.add(int(mm.group(0)))
            for t in client.category_members("Sudirman Cup"):
                mm = YEAR_RE.match(t)
                if mm and in_range(t):
                    sud.add(int(mm.group(0)))
            plan = ([(f"{y} Thomas Cup", "thomas") for y in sorted(tu)]
                    + [(f"{y} Uber Cup", "uber") for y in sorted(tu)]
                    + [(f"{y} Sudirman Cup", "sudirman") for y in sorted(sud)])
            self.stdout.write(f"[cups] {len(tu)} Thomas/Uber years, {len(sud)} Sudirman")
            for title, cup in plan:
                try:
                    n = self._one_team(client, title, cup, o["refresh"],
                                       players, tourns, matches)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ! {title}: {e}")); continue
                if n:
                    tot_t += 1; tot_m += n
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {title}: {n} rubbers"))
            client.close()
            self.stdout.write(self.style.SUCCESS(f"Done: {tot_t} cups, {tot_m} rubbers."))
            return

        if o["games"]:
            # multi-sport events aren't in BWF data at any year -> pull all
            gyf, gyt = (yf, yt) if (yf, yt) != (1983, 2006) else (1948, 2024)
            def game_year_ok(t):
                m = YEAR_RE.match(re.sub(r"^Badminton at the ", "", t))
                return bool(m) and gyf <= int(m.group(0)) <= gyt
            jobs = []
            for cat, tier in GAMES.items():
                for t in client.category_members(cat):
                    if re.match(r"^Badminton at the \d{4}\b", t) and game_year_ok(t):
                        jobs.append((t, tier))
            jobs += [(f"Badminton at the {y} Southeast Asian Games", "SEA Games")
                     for y in SEA_YEARS if gyf <= y <= gyt]
            self.stdout.write(f"[games] {len(jobs)} editions in {gyf}-{gyt}")
            for title, tier in jobs:
                try:
                    n = self._one(client, title, tier, o["refresh"],
                                  players, tourns, matches, team=True)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ! {title}: {e}")); continue
                if n:
                    tot_t += 1; tot_m += n
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {title}: {n} matches"))
            client.close()
            self.stdout.write(self.style.SUCCESS(f"Done: {tot_t} events, {tot_m} matches."))
            return

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
            self.stderr.write("give --pages, --category, --all-majors, or --cups"); return

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

    def _one(self, client, title, tier, refresh, players, tourns, matches, team=False):
        """Fetch + parse + ingest one tournament. Returns match count or None.
        team=True also pulls team-event rubbers ("– Men's team" etc.)."""
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
            parsed = parsed + self._subarticles(client, title)
        if team:
            parsed = parsed + self._team_subarticles(client, title)
        parsed = [m for m in wiki_parse.dedupe(parsed) if m["winner_side"]]
        if not parsed:
            return None
        return self._ingest(title, tier, wt, parsed, players, tourns, matches)

    def _team_subarticles(self, client, title):
        """Team events within a multi-sport games ("– Men's/Women's/Mixed team")."""
        out = []
        for disc, cup in TEAM_SUBS:
            for sep in ("–", "-"):
                wt = client.wikitext(f"{title} {sep} {disc}")
                if wt:
                    out += wiki_parse.parse_team_ties(wt, cup)
                    break
        return out

    def _one_team(self, client, title, cup, refresh, players, tourns, matches):
        """Ingest one team cup. Rubbers come from the cup-specific stage
        sub-articles ('{title} group/knockout stage'); the main article (which
        may be a combined Thomas & Uber page) is used only for name/dates, and
        parsed for rubbers only when it isn't a combined article."""
        if refresh:
            for s in (title, f"{title} group stage", f"{title} knockout stage"):
                cp = client._cache_path(s)
                if cp.exists():
                    cp.unlink()
        main_wt = client.wikitext(title)
        parsed = []
        for stage in ("group stage", "knockout stage"):
            wt = client.wikitext(f"{title} {stage}")
            if wt:
                parsed += wiki_parse.parse_team_ties(wt, cup)
        # fallback to the main article only if it's not a combined T&U page
        combined = main_wt and "Thomas Cup" in main_wt and "Uber Cup" in main_wt
        if not parsed and main_wt and not combined:
            parsed += wiki_parse.parse_team_ties(main_wt, cup)
        parsed = [m for m in wiki_parse.dedupe(parsed) if m["winner_side"]]
        if not parsed:
            return None
        tier = {"thomas": "Thomas Cup", "uber": "Uber Cup",
                "sudirman": "Sudirman Cup"}[cup]
        meta_wt = main_wt or ""
        return self._ingest(title, tier, meta_wt, parsed, players, tourns, matches)

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
        # fall back to the year in the title (mid-year) when the infobox has no
        # date — critical so historical tournaments sort chronologically.
        ym = YEAR_RE.match(title)
        year_default = parse_date(f"{ym.group(0)}-06-01") if ym else None
        t.start_date = meta["start"] or year_default
        t.end_date = meta["end"] or t.start_date
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
            # No per-match times on Wikipedia: derive a chronological timestamp
            # from the tournament date + round, so history sorts by date then
            # round (and the engine processes periods in the right order).
            match.match_time_utc = (
                datetime.combine(t.start_date, dt_time(), tzinfo=dt_tz.utc)
                + timedelta(minutes=rorder) if t.start_date else None)
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
