"""Infer a team-cup rubber's true discipline from its lineup.

Team-cup articles (Thomas/Uber/Sudirman) list rubbers in play order, and the
scraper assigns a discipline by POSITION — which does not match who actually
played (a singles star can appear in the "doubles" slot). The reliable signal is
the lineup itself: player count gives singles vs doubles, and player gender
distinguishes MS/WS and MD/WD/XD. Returns None when the needed genders are
unknown, so callers can leave such rubbers untouched rather than guess.
"""
from __future__ import annotations


def rubber_discipline(side1, side2):
    """MS | WS | MD | WD | XD, or None if undeterminable. side1/side2 are lists
    of Player objects (each with a `.gender` of 'M', 'F', or '')."""
    n = max(len(side1), len(side2))
    if n == 0:
        return None
    if n == 1:
        g = (side1[0].gender if side1 else "") or (side2[0].gender if side2 else "")
        return {"M": "MS", "F": "WS"}.get(g)
    # Doubles: read the genders off whichever side has two players.
    side = side1 if len(side1) == 2 else side2
    gs = [p.gender for p in side if p.gender]
    if len(gs) < 2:
        return None  # need both partners' genders to tell MD/WD from XD
    if "M" in gs and "F" in gs:
        return "XD"
    if all(x == "M" for x in gs):
        return "MD"
    if all(x == "F" for x in gs):
        return "WD"
    return None
