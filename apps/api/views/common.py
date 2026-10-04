"""Shared helpers for the read API: discipline constants, tournament prestige,
the active-player cutoff, compact match cards and in-process sub-requests."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.ingest.boards import ACTIVE_DAYS

from ..serializers import PlayerBriefSerializer

EVENTS = ("MS", "WS", "MD", "WD", "XD")


DOUBLES = ("MD", "WD", "XD")


def team_cup_kind(t):
    """'thomas' | 'uber' | 'sudirman' | 'team' | None — is this tournament a
    team competition (nation vs nation, rubbers grouped into ties)?"""
    hay = f"{t.name or ''} {t.category_name or ''}".lower()
    if "sudirman cup" in hay:
        return "sudirman"
    if "thomas cup" in hay:
        return "thomas"
    if "uber cup" in hay:
        return "uber"
    if "team championship" in hay or "team event" in hay or (
        "team" in hay and "cup" in hay
    ):
        return "team"
    return None


def _side_country(players):
    """The country a rubber side represents: the most common player country."""
    from collections import Counter

    c = Counter(p.country_code for p in players if p.country_code)
    return c.most_common(1)[0][0] if c else None


def _rubber_discipline(s1, s2):
    """Discipline of a team-cup rubber for display: the gender-inferred value,
    or a bare S/D from player count when gender is unknown."""
    from apps.ingest.cup_events import rubber_discipline

    return rubber_discipline(s1, s2) or ("S" if max(len(s1), len(s2)) == 1 else "D")


# Full tournament prestige order (top = most prestigious). Multi-sport events and
# team cups sit above the BWF World Tour, then development tiers. Anything
# unlisted sorts last. Used by the tournament "master" (by-year) overview.
# Tournament sections follow BWF's official grading (Wikipedia "BWF events"):
#   Grade 1 (S-Tier) — WC, Thomas/Uber/Sudirman, Olympics, + Junior/Senior/Para
#   Continental Games — Asian/SEA/Commonwealth/etc. multi-sport & continental
#   Grade 2 (A-Tier)  — BWF World Tour (Finals, Super 1000..100) + predecessors
#   Grade 3 (B-Tier)  — Continental Circuit (Int'l Challenge/Series/Future)
GRADE1 = {
    "Olympics", "World Championships",
    "Thomas Cup", "Uber Cup", "Sudirman Cup",
    "Grade 1 – Individual Tournaments", "Grade 1 – Team Tournaments",
    "Grade 1 – Individual Senior Tournaments",
}


CONTINENTAL = {
    "Asian Games", "Commonwealth Games", "European Games", "Pan American Games",
    "African Games", "SEA Games", "Continental Individual Games",
    "Continental Team Games", "Continental Individual Championships",
    "Continental Team Championships",
}


PRESTIGE_ORDER = [
    # Grade 1 (S-Tier) — Main then Others
    "Olympics", "World Championships",
    "Thomas Cup", "Uber Cup", "Sudirman Cup",
    "Grade 1 – Individual Tournaments", "Grade 1 – Team Tournaments",
    "Grade 1 – Individual Senior Tournaments",
    # Continental Games
    "Asian Games", "Commonwealth Games", "European Games",
    "Pan American Games", "African Games", "SEA Games",
    "Continental Individual Games", "Continental Team Games",
    "Continental Individual Championships", "Continental Team Championships",
    # Grade 2 (BWF World Tour) — by level
    "HSBC BWF World Tour Finals", "World Tour Finals",
    "HSBC BWF World Tour Super 1000", "All England",
    "HSBC BWF World Tour Super 750", "HSBC BWF World Tour Super 500",
    "HSBC BWF World Tour Super 300", "BWF Tour Super 100",
    "World Superseries Premier", "World Superseries",
    "Grand Prix Gold", "Grand Prix",
    # Grade 3 (Continental Circuit)
    "International Challenge", "International Series", "Future Series",
    "BWF Events", "Other",
]


_PRESTIGE_RANK = {name: i for i, name in enumerate(PRESTIGE_ORDER)}


# Broad section a tier belongs to (for the master view's group headers).
def prestige_group(category: str) -> str:
    if category in GRADE1:
        return "🥇 Grade 1 (S-Tier)"
    if category in CONTINENTAL:
        return "🌏 Continental Games"
    if any(k in category for k in ("World Tour", "Superseries", "Grand Prix",
                                   "All England", "Super 100")):
        return "🌐 Grade 2 · BWF World Tour"
    return "🏸 Grade 3 · Continental Circuit"


def active_cutoff():
    """Anything last active before this is 'retired' — excluded from CURRENT
    rankings (still counted in all-time/peak). Measured from the latest match in
    the data (data-relative), so the rule holds even if collection pauses.
    Stored on the DataVersion at each bump, so it costs a PK lookup."""
    from apps.ingest.dataversion import current

    dv = current()
    if dv is not None and dv.active_cutoff is not None:
        return dv.active_cutoff
    return timezone.now() - timedelta(days=ACTIVE_DAYS)


def _team_rating(members):
    """Conservative side rating (mean mu − 2·RMS rd), rounded. None if no data."""
    from rating.predict import conservative, team_rating

    t = team_rating(members)
    return round(conservative(*t)) if t else None


def _match_card(m):
    """Compact match descriptor: both sides (as pairs), score, tournament, round."""
    lineup = sorted(m.lineup.all(), key=lambda l: l.side)
    side1 = [l.player for l in lineup if l.side == 1]
    side2 = [l.player for l in lineup if l.side == 2]
    games = [
        [g.side1_points, g.side2_points]
        for g in sorted(m.games.all(), key=lambda g: g.game_no)
    ]
    return {
        "match_id": m.match_id,
        "event": m.event,
        "round_name": m.round_name,
        "match_time_utc": m.match_time_utc,
        "tournament": {"id": m.tournament_id, "name": m.tournament.name},
        "winner_side": m.winner_side,
        "score": games,
        "side1": PlayerBriefSerializer(side1, many=True).data,
        "side2": PlayerBriefSerializer(side2, many=True).data,
    }


def _subcall(request, path: str, **params):
    """Run another public GET view in-process and return its payload, so a
    composite endpoint reuses each view exactly (no duplicated logic)."""
    from django.http import HttpRequest, QueryDict
    from django.urls import resolve

    sub = HttpRequest()
    sub.method = "GET"
    sub.path = sub.path_info = path
    sub.META = {**request.META, "QUERY_STRING": ""}
    sub.GET = QueryDict(mutable=True)
    for k, v in params.items():
        sub.GET[k] = str(v)
    match = resolve(path)
    resp = match.func(sub, *match.args, **match.kwargs)
    if resp.status_code != 200:
        return None
    return resp.data
