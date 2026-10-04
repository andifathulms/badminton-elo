"""`manage.py scrape_dewiki` — backfill 1983-2005 from German Wikipedia.

English Wikipedia usually has only the finals of an old event; German
Wikipedia lists every match (apps/ingest/dewiki_parse.py). Tournaments are
enumerated from the per-year category "Kategorie:Badminton {year}" and kept to
the event types the BWF-API era also covers — international opens, Grand
Prix, internationals, continental and world championships, multi-sport games
— not national championships, club leagues, junior/senior or student events.

Players: a German page links to its English one (langlinks), so a player
lands on the same record as the English-Wikipedia backfill (wiki_title = the
English title). Players with no English page are keyed "de:<German title>".
Run `reconcile_players --apply` afterwards to fold them onto BWF ids, and
`dedup_tournaments --apply` to merge overlaps with English/API copies.

    python manage.py scrape_dewiki [--from 1983 --to 2005] [--pages "All England 1985;…"]
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_tz

from django.db import transaction

from apps.ingest.dewiki_parse import parse_article, start_date
from apps.ingest.management.base import DataCommand
from apps.ingest.management.commands.reconcile_players import COUNTRY_CANON
from apps.ingest.management.commands.scrape_wiki import Allocator, clean_name
from apps.ingest.models import Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.wiki_client import WikiClient

EXCLUDE = re.compile(
    r"bundesliga|\bliga\b|junior|jugend|schüler|\bu ?1\d\b|senior|veteran|"
    r"hochschul|universi|studenten|europapokal|helvetia|mannschaft|"
    r"thomas cup|uber cup|sudirman|länderspiel", re.I)
NATIONAL = re.compile(r"badmintonmeisterschaft", re.I)
INTERNATIONAL_CHAMPS = re.compile(
    r"europa|asien|welt|panamerika|afrika|ozeanien|commonwealth|nordische|"
    r"südamerika|carebaco|zentralamerika|balkan|südostasien", re.I)
SUBPAGE = {"herreneinzel": "Herreneinzel", "dameneinzel": "Dameneinzel",
           "herrendoppel": "Herrendoppel", "damendoppel": "Damendoppel", "mixed": "Mixed"}


def wanted(title: str) -> bool:
    if EXCLUDE.search(title):
        return False
    if NATIONAL.search(title) and not INTERNATIONAL_CHAMPS.search(title):
        return False  # e.g. 'Dänische Badmintonmeisterschaft 1995'
    return bool(re.search(r"\b(19|20)\d\d\b", title))


def tier_of(title: str, grand_prix: set[str]) -> str:
    low = title.lower()
    if "all england" in low:
        return "All England"
    if title in grand_prix:
        return "Grand Prix"
    if "weltmeisterschaft" in low or "world championships" in low:
        return "World Championships"
    if "olympi" in low:
        return "Olympics"
    if re.search(r"spiele|games", low):
        return "Continental Individual Games"
    if "meisterschaft" in low or "championships" in low:
        return "Continental Individual Championships"
    if "international" in low:
        return "International Series"
    return "Other"


def scoring_code(games) -> str:
    """Side-out era: '5x7' for the 2001-02 to-7 trial, else '15x3s'."""
    real = [max(a, b) for a, b in games if a or b]
    if real and max(real) <= 10 and len(real) >= 3:
        return "5x7"
    return "15x3s"


class Command(DataCommand):
    help = "Backfill pre-2006 tournaments from German Wikipedia match lists."

    def add_arguments(self, p):
        p.add_argument("--from", type=int, dest="yr_from", default=1983)
        p.add_argument("--to", type=int, dest="yr_to", default=2005)
        p.add_argument("--pages", help="explicit German article titles, ;-separated")

    def handle(self, *a, **o):
        self.players = Allocator(Player)
        self.tourns = Allocator(Tournament)
        self.matches = Allocator(Match)
        tot_t = tot_m = 0
        with WikiClient(lang="de") as de, WikiClient() as en:
            self.de, self.en = de, en
            if o["pages"]:
                jobs = [(t.strip(), set()) for t in o["pages"].split(";") if t.strip()]
            else:
                jobs = []
                for y in range(o["yr_from"], o["yr_to"] + 1):
                    gp = set(de.category_members(f"Kategorie:World Badminton Grand Prix {y}"))
                    for t in de.category_members(f"Kategorie:Badminton {y}"):
                        if wanted(t):
                            jobs.append((t, gp))
            # Per-discipline subpages ('…(Badminton)/Herreneinzel') join their base.
            grouped: dict[str, list[str]] = {}
            gp_of: dict[str, set] = {}
            for t, gp in jobs:
                base = t.split("/")[0]
                grouped.setdefault(base, []).append(t)
                gp_of[base] = gp
            self.stdout.write(f"[dewiki] {len(grouped)} tournaments to read")
            for base, titles in grouped.items():
                try:
                    n = self._one(base, titles, gp_of[base])
                except Exception as e:  # noqa: BLE001 - one bad article must not stop the sweep
                    self.stdout.write(self.style.WARNING(f"  ! {base}: {e}"))
                    continue
                if n:
                    tot_t += 1
                    tot_m += n
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {base}: {n} matches"))
        self.stdout.write(self.style.SUCCESS(f"Done: {tot_t} tournaments, {tot_m} matches."))

    def _text(self, title: str) -> str:
        wt = self.de.wikitext(title) or ""
        if "/" in title:  # subpage: its discipline is in the title, not a heading
            sub = title.rsplit("/", 1)[1].strip().lower()
            heading = SUBPAGE.get(sub)
            if heading:
                wt = f"== {heading} ==\n{wt}"
        return wt

    def _one(self, base: str, titles: list[str], grand_prix: set[str]) -> int:
        texts = [self._text(t) for t in titles]
        parsed = [m for wt in texts for m in parse_article(wt)]
        if not parsed:
            return 0
        ym = re.search(r"\b((?:19|20)\d\d)\b", base)
        year = int(ym.group(1)) if ym else None
        start = next((d for d in (start_date(wt, year) for wt in texts) if d), None)
        if start is None and year:
            start = date(year, 6, 1)
        de_titles = [p[0] for m in parsed for p in m["side1"] + m["side2"]]
        en_of = self.de.langlinks(de_titles + [base])
        return self._ingest(base, en_of.get(base), start, tier_of(base, grand_prix), parsed, en_of)

    def _player(self, de_title: str, display: str, en_title: str | None, country):
        key = en_title or f"de:{de_title}"
        p = Player.objects.filter(wiki_title=key).first()
        if p is None and not en_title:
            # an unlinked name the English backfill already stored verbatim
            p = Player.objects.filter(wiki_title=display).first()
        if p is None:
            p = Player(player_id=self.players.next(), wiki_title=key,
                       name_display=clean_name(en_title or de_title) or display)
        if country and not p.country_code:
            p.country_code = country
        p.country_code = COUNTRY_CANON.get(p.country_code, p.country_code)  # ISO -> IOC
        p.save()
        return p

    @transaction.atomic
    def _ingest(self, base, en_title, start, tier, parsed, en_of) -> int:
        code = f"dewiki:{base}"
        t = Tournament.objects.filter(code=code).first() or Tournament(
            tournament_id=self.tourns.next(), code=code)
        t.name = clean_name(en_title) if en_title else base
        t.start_date = start
        t.end_date = start
        t.category_name = tier
        t.save()
        n = 0
        for m in parsed:
            s1 = "+".join(sorted(p[0] for p in m["side1"]))
            s2 = "+".join(sorted(p[0] for p in m["side2"]))
            skey = f"{code}:{m['event']}:{m['stage']}:{m['round_name']}:{s1}|{s2}"[:255]
            match = Match.objects.filter(source_key=skey).first() or Match(
                match_id=self.matches.next(), source_key=skey)
            match.tournament = t
            match.event = m["event"]
            match.round_name = m["round_name"]
            match.round_order = m["round_order"]
            match.match_time_utc = (datetime.combine(start, dt_time(), tzinfo=dt_tz.utc)
                                    + timedelta(minutes=m["round_order"])) if start else None
            match.score_status = m["status"]
            match.winner_side = m["winner_side"]
            match.side1_country = COUNTRY_CANON.get(m["side1"][0][2] or "", m["side1"][0][2] or "")
            match.side2_country = COUNTRY_CANON.get(m["side2"][0][2] or "", m["side2"][0][2] or "")
            match.scoring_format = scoring_code(m["games"]) if m["games"] else ""
            match.rating_excluded = m["status"] == "Walkover" or not m["games"]
            match.save()
            match.games.all().delete()
            match.lineup.all().delete()
            for gi, (a, b) in enumerate(m["games"], 1):
                Game.objects.create(match=match, game_no=gi, side1_points=a, side2_points=b)
            for side, players in ((1, m["side1"]), (2, m["side2"])):
                for de_title, display, country in players:
                    p = self._player(de_title, display, en_of.get(de_title), country)
                    MatchPlayer.objects.get_or_create(match=match, side=side, player=p)
            n += 1
        return n
