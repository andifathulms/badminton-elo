"""Team-cup ties: rubbers grouped into nation-vs-nation ties (a service).

Used live by the ties endpoint and ahead of time by `manage.py build_ties`,
which stores the payload per team cup (TournamentTies) after every re-rate.
"""
from __future__ import annotations

from apps.ingest.models import Match

from .elo import tournament_match_elo
from .serializers import PlayerBriefSerializer
from .views.common import EVENTS, _side_country, team_cup_kind


def build_ties(t) -> dict:
    """A team cup as nation-vs-nation ties (the /tournaments/{id}/ties payload).

    Rubbers (individual matches) are grouped into ties: within a round, the
    rubbers between the same pair of countries form one tie. Each rubber's true
    discipline is inferred from its lineup (the stored `event` is unreliable on
    team cups). Sides are oriented so country1 reads first. Precomputed for
    every team cup by `build_ties` (it depends on ratings), computed live for
    anything else.
    """
    kind = team_cup_kind(t)
    matches = list(
        Match.objects.filter(tournament=t)
        .prefetch_related("lineup__player", "games")
        .order_by("round_order", "match_id")
    )
    elo_map = tournament_match_elo(t.tournament_id)

    # Bucket by round, preserving round order.
    rounds: dict = {}
    for m in matches:
        rounds.setdefault((m.round_order or 0, m.round_name), []).append(m)

    def side_elo(mid, players):
        ds = [elo_map.get(mid, {}).get(p.player_id) for p in players]
        ds = [d[2] for d in ds if d]
        return round(sum(ds) / len(ds), 1) if ds else None

    from apps.ingest.cup_events import rubber_discipline

    # Old editions bundle Thomas (men) + Uber (women) into ONE article, so
    # the cup label is ambiguous there — trust gender in that case.
    _name = (t.name or "").lower()
    combined = "thomas" in _name and "uber" in _name

    def disc_of(s1, s2):
        g = rubber_discipline(s1, s2)   # gender-based; None if unknown
        if g:
            return g
        singles = max(len(s1), len(s2)) == 1
        # Fall back to the cup's single gender only when it's unambiguous.
        if not combined and kind == "thomas":
            return "MS" if singles else "MD"
        if not combined and kind == "uber":
            return "WS" if singles else "WD"
        return "S" if singles else "D"

    def build_rubber(m, s1, s2, c1, c2, country1, country2, order):
        games = [
            [g.side1_points, g.side2_points]
            for g in sorted(m.games.all(), key=lambda g: g.game_no)
        ]
        win = m.winner_side
        # Orient so country1's players read as side1. Works even when a side's
        # country is unknown, by matching against the tie's two nations.
        swap = (c1 is not None and c1 == country2) or (c2 is not None and c2 == country1)
        if swap:
            s1, s2 = s2, s1
            games = [[b, a] for a, b in games]
            win = {1: 2, 2: 1}.get(win)
        return {
            "match_id": m.match_id,
            "order": order,
            # Trust the stored discipline (set at ingest from the source's
            # matchTypeValue or the draw's gender) — it's authoritative. Only
            # re-infer from player genders when it isn't a clean code, so a
            # rubber never shows a bare "S"/"D" when its event is really MD.
            "discipline": m.event if m.event in EVENTS else disc_of(s1, s2),
            "side1": PlayerBriefSerializer(s1, many=True).data,
            "side2": PlayerBriefSerializer(s2, many=True).data,
            "winner_side": win,
            "score": games,
            "score_status": m.score_status,
            "elo1": side_elo(m.match_id, s1),
            "elo2": side_elo(m.match_id, s2),
        }

    out_rounds = []
    champion = None
    for (rorder, rname), ms in sorted(rounds.items()):
        parsed = []
        for m in ms:
            s1 = [l.player for l in m.lineup.all() if l.side == 1]
            s2 = [l.player for l in m.lineup.all() if l.side == 2]
            # Prefer the nation stored on the match (nation-at-the-time from the
            # source); fall back to the players' present-day country_code.
            c1 = m.side1_country or _side_country(s1)
            c2 = m.side2_country or _side_country(s2)
            parsed.append((m, s1, s2, c1, c2))

        # Group by the UNORDERED pair of nations, not by adjacency — a tie's
        # rubbers can be interleaved with other ties in the schedule, so a
        # consecutive-run grouping would split them. Rubbers whose opponent
        # has no country_code are attached afterwards.
        by_pair: dict = {}          # frozenset({c1,c2}) -> tie bucket
        order: list = []            # first-seen order of pairs
        pending: list = []
        for idx, (m, s1, s2, c1, c2) in enumerate(parsed):
            known = [c for c in (c1, c2) if c]
            if len(known) == 2:
                key = frozenset(known)
                if key not in by_pair:
                    by_pair[key] = {"countries": set(known), "rubbers": []}
                    order.append(key)
                by_pair[key]["rubbers"].append((idx, m, s1, s2, c1, c2))
            else:
                pending.append((idx, m, s1, s2, c1, c2))

        # Attach unknown-opponent rubbers to the right tie: the one containing
        # their known nation (nearest by schedule order when several match).
        for row in pending:
            idx, m, s1, s2, c1, c2 = row
            k = c1 or c2
            cands = [key for key in by_pair if (k in key if k else True)]
            if len(cands) == 1:
                key = cands[0]
            elif len(cands) > 1:
                key = min(cands, key=lambda ky: min(
                    abs(idx - r[0]) for r in by_pair[ky]["rubbers"]))
            else:
                key = frozenset([k]) if k else frozenset([f"?{idx}"])
                if key not in by_pair:
                    by_pair[key] = {"countries": set([k] if k else []),
                                    "rubbers": []}
                    order.append(key)
            by_pair[key]["rubbers"].append(row)

        ties = []
        for i, key in enumerate(order, 1):
            rt = by_pair[key]
            rows = sorted(rt["rubbers"], key=lambda x: x[0])
            cs = rt["countries"]
            f = rows[0]
            country1 = (f[4] if f[4] in cs else f[5] if f[5] in cs
                        else next(iter(cs), None))
            country2 = next((c for c in cs if c != country1), None)
            rubbers, s1c, s2c = [], 0, 0
            for j, (_, m, s1, s2, c1, c2) in enumerate(rows, 1):
                r = build_rubber(m, s1, s2, c1, c2, country1, country2, j)
                rubbers.append(r)
                if r["winner_side"] == 1:
                    s1c += 1
                elif r["winner_side"] == 2:
                    s2c += 1
            ties.append({
                "order": i,
                "country1": country1, "country2": country2,
                "score1": s1c, "score2": s2c,
                "winner_country": (country1 if s1c > s2c
                                   else country2 if s2c > s1c else None),
                "rubbers": rubbers,
            })
        out_rounds.append({
            "round_name": rname, "round_order": rorder, "ties": ties,
        })
        if rname in ("Final", "F") and len(ties) == 1:
            champion = ties[0]["winner_country"]

    return {
        "is_team_cup": kind is not None,
        "cup": kind,
        "champion": champion,
        "rounds": out_rounds,
    }
