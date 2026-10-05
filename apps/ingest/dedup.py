"""Find the same tournament ingested from two sources (Wikipedia + BWF API).

Wikipedia filled the pre-2006 gap, but some articles also covered events the
BWF API has (Sudirman Cups, 2005/2006 Worlds, Thomas & Uber 2008-2012, ...),
so those contests were rated twice. The API copy is authoritative (real
player ids, rounds, times); a Wikipedia match duplicates an API match when it
has the same game scores in the same discipline, or the same players by name (case, accents and
name order ignored — catches retirements and garbled Wikipedia scores).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import timedelta

from .models import Match, Tournament
from .wiki_parse import is_bye

WINDOW = timedelta(days=10)
YEAR_FALLBACK_MIN = 10  # wiki matches needed before a year-wide search
# Letters NFKD doesn't decompose (it would DROP them: 'Trần Đình' -> 'trn inh').
_FOLD = str.maketrans({"đ": "d", "ø": "o", "æ": "ae", "ß": "ss", "ł": "l", "ð": "d",
                       "þ": "th", "œ": "oe", "ı": "i"})
MIN_SHARE = 0.8  # of the wiki copy's matches that must duplicate the API copy
# For a wiki SUPERSET only exact duplicates are deleted, so this only guards
# against coincidental overlap (unplayed/unparsed rubbers lower the share).
CONTAIN_SHARE = 0.5
UNION_SHARE = 0.6  # leftovers: share duplicating the window's API events


def norm_name(name: str) -> str:
    """A player's name as its sorted letters: robust to case, accents, word
    order and spacing ("CHEN Yu Fei" == "Chen Yufei" == "Yufei CHEN")."""
    s = (name or "").lower().translate(_FOLD)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(sorted(re.findall(r"[a-z]", s)))


def match_signatures(tournament_ids) -> dict[int, dict]:
    """{match_id: {tid, score, names, bye, plausible}} for every match of the
    given tournaments, from three bulk queries."""
    from .models import Game, MatchPlayer

    tids = list(tournament_ids)
    out: dict[int, dict] = {}
    for mid, tid, event in Match.objects.filter(tournament_id__in=tids).values_list(
            "match_id", "tournament_id", "event").iterator():
        out[mid] = {"tid": tid, "event": event, "games": [], "sides": defaultdict(list)}
    for mid, no, a, b in Game.objects.filter(match__tournament_id__in=tids).values_list(
            "match_id", "game_no", "side1_points", "side2_points").iterator():
        out[mid]["games"].append((no, a, b))
    for mid, side, name, wt in MatchPlayer.objects.filter(
            match__tournament_id__in=tids).values_list(
            "match_id", "side", "player__name_display", "player__wiki_title").iterator():
        out[mid]["sides"][side].append((name, wt))
    for rec in out.values():
        games = sorted(rec.pop("games"))
        sides = rec.pop("sides")
        # Scores only identify a contest within one discipline (common lines
        # like 21-15 21-12 recur across a big field).
        rec["score"] = (rec["event"] + ":" + "|".join(f"{min(a, b)}-{max(a, b)}" for _, a, b in games)
                        if games else "")
        rec["names"] = frozenset(frozenset(norm_name(n) for n, _ in ps) for ps in sides.values())
        rec["bye"] = any(is_bye(n) or is_bye(w) for ps in sides.values() for n, w in ps)
        # No game where nobody reached 11 (Wikipedia sometimes holds set counts).
        rec["plausible"] = all(max(a, b) >= 11 for _, a, b in games)
    return out


# Source priority, most authoritative first. A copy is compared against every
# MORE authoritative source: German Wikipedia yields to the BWF API, English
# Wikipedia to both (German lists every match; English often only finals).
# Last, a German FINALS-ONLY copy (< SMALL matches, from a 'Finalergebnisse'
# table) yields to any fuller copy — e.g. the English 1986 Commonwealth Games
# bracket holds the five finals the German article lists.
SMALL = 10
SOURCES = (("dewiki:", ("wiki:", "dewiki:"), None), ("wiki:", ("wiki:",), None),
           ("dewiki:", ("dewiki:",), SMALL))



def _best_overlap(w, apis, wrecs, api_index):
    """(w, api, plan) for the candidate holding the most of `w`'s matches,
    if that is >= MIN_SHARE of them; else None."""
    best = None
    for a in apis:
        scores, names = api_index(a.tournament_id)
        plan = {"dup": [], "bye": [], "move": [], "drop": []}
        for mid, r in wrecs.items():
            if r["bye"]:
                plan["bye"].append(mid)
            elif (r["score"] and r["score"] in scores) or r["names"] in names:
                plan["dup"].append(mid)
            elif r["plausible"]:
                plan["move"].append(mid)
            else:
                plan["drop"].append(mid)
        real = len(wrecs) - len(plan["bye"])
        if real and len(plan["dup"]) / real >= MIN_SHARE:
            if best is None or len(plan["dup"]) > len(best[2]["dup"]):
                best = (w, a, plan)
    return best


def find_pairs(source: str = "wiki:", weaker: tuple[str, ...] = ("wiki:",),
               max_matches: int | None = None):
    """[(copy Tournament, authoritative Tournament | None, plan)] where plan =
    {dup, bye, move, drop} lists of match ids, for copies whose code starts with
    `source`, against tournaments whose code starts with none of `weaker`.
    `max_matches` limits it to copies with fewer matches than that."""
    wikis = Tournament.objects.filter(code__startswith=source, match_count__gt=0,
                                      start_date__isnull=False)
    if max_matches:
        wikis = wikis.filter(match_count__lt=max_matches)
    wikis = list(wikis)
    api_sigs: dict[int, tuple[set, set]] = {}

    def api_index(tid):
        if tid not in api_sigs:
            recs = match_signatures([tid]).values()
            api_sigs[tid] = ({r["score"] for r in recs if r["score"]}, {r["names"] for r in recs})
        return api_sigs[tid]

    out = []
    for w in wikis:
        if (w.start_date.month, w.start_date.day) == (6, 1):
            # No infobox date: scrape_wiki defaulted it to 1 June of the
            # title's year, so look across that whole year.
            near = {"start_date__year": w.start_date.year}
        else:
            near = {"start_date__gte": w.start_date - WINDOW,
                    "start_date__lte": w.start_date + WINDOW}
        apis = Tournament.objects.filter(match_count__gt=0, **near)
        for prefix in weaker:
            apis = apis.exclude(code__startswith=prefix)
        wrecs = match_signatures([w.tournament_id])
        best = _best_overlap(w, apis, wrecs, api_index)
        if best is None and "start_date__gte" in near and len(wrecs) >= YEAR_FALLBACK_MIN:
            # A wrong infobox date (1996 Olympics: '1 July') puts the copy
            # outside the window. A big enough copy that is >= MIN_SHARE
            # duplicate is the same event wherever it sits in the year.
            wide = Tournament.objects.filter(match_count__gt=0,
                                             start_date__year=w.start_date.year)
            for prefix in weaker:
                wide = wide.exclude(code__startswith=prefix)
            best = _best_overlap(w, wide.exclude(pk__in=apis), wrecs, api_index)
        if best:
            out.append(best)
            continue
        # The wiki copy may be a SUPERSET: a Games article holds the individual
        # draws AND the team rubbers, while the API has only the team events
        # (2022 Asian Games). Drop just the rubbers of any API tournament the
        # wiki copy contains (>= CONTAIN_SHARE of it), and keep the rest.
        dropped: set[int] = set()
        for a in apis:
            a_recs = match_signatures([a.tournament_id])
            if len(a_recs) < 10:
                continue
            year_wide = "start_date__gte" not in near
            # Lists, not dicts: several wiki matches can share a scoreline,
            # and each API match should claim exactly one wiki match.
            w_by_score: dict = defaultdict(list)
            w_by_name: dict = defaultdict(list)
            for mid, r in wrecs.items():
                if r["score"]:
                    w_by_score[r["score"]].append(mid)
                w_by_name[r["names"]].append(mid)
            hits = set()
            for r in a_recs.values():
                # Over a whole year, scorelines alone coincide: names only.
                pool = w_by_name.get(r["names"], []) + (
                    w_by_score.get(r["score"], []) if r["score"] and not year_wide else [])
                mid = next((m for m in pool if m not in hits and m not in dropped), None)
                if mid:
                    hits.add(mid)
            if len(hits) / len(a_recs) >= CONTAIN_SHARE:
                dropped |= hits
        # Leftovers of an earlier merge: most of the wiki copy duplicates the
        # UNION of the window's API tournaments (individual + team splits).
        # Only for a real date (a 10-day window) and on NAMES only: across a
        # whole year of events, common scorelines (21-15 21-12) coincide.
        if not dropped and "start_date__gte" in near:
            u_names = set()
            for a in apis:
                u_names |= api_index(a.tournament_id)[1]
            union_dups = {mid for mid, r in wrecs.items() if r["names"] in u_names}
            if wrecs and len(union_dups) / len(wrecs) >= UNION_SHARE:
                dropped = union_dups
        if dropped:
            out.append((w, None, {"dup": sorted(dropped), "bye": [], "move": [], "drop": []}))
    return out
