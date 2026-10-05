"""Side-out scoring (pre-2006) as a likelihood for the points engine. Pure.

Before 2006 only the SERVER scored: losing a rally on serve just passed the
serve ("side-out"). Games were to 15 (women's singles to 11; the 2002-05
trial to 7) with "setting" near the end. A 15-3 game says much more than
"won" — the winner kept the serve and the loser almost never held it — but
its points are not rallies, so the rally likelihood that `points.py` uses for
21-point scoring can't read them.

This module turns the rally probability p (from the rating gap, exactly as in
`points.py`) into the probability of each observed GAME score by walking the
side-out rules as a Markov chain over (a, b, server, hand):

  * the server scores by winning the rally and keeps serving on that hand;
    a lost rally passes to the partner's hand (doubles) or to the other side;
  * the side that starts a game has one hand only ("first hand down");
  * game 1's first server is unknown (both averaged); a later game is started
    by the previous game's winner.

Outcomes of one game: won/lost to exactly L points (L <= target-3), or a
CLOSE game — both sides reached target-2 — modelled as a race to
`DEUCE_RACE` more points (setting rules varied by event and by choice, so
that bucket keeps only who won). The outcome probabilities sum to 1.

`game_terms(p, games, doubles)` returns the match's log-likelihood slope and
Fisher information in p; `points.py` turns them into the Glicko step.
"""
from __future__ import annotations

from functools import lru_cache
from math import comb

GRID = 800  # p-grid resolution for the cached outcome tables
DEUCE_RACE = 3


def target_of(winner_points: int) -> int | None:
    """Game target from the winner's score: 7/8 -> 7; 11-13 -> 11; 15-18 -> 15."""
    if winner_points in (7, 8):
        return 7
    if 11 <= winner_points <= 13:
        return 11
    if 15 <= winner_points <= 18:
        return 15
    return None


def _race(p: float, n: int) -> float:
    """P(first to n points) when every point is won with probability p."""
    q = 1.0 - p
    return sum(comb(n - 1 + k, k) * p ** n * q ** k for k in range(n))


def _scorer_dist(p: float, full: int, a_srv: bool, h: int):
    """At a fixed score, from server (a_srv, hand h): [(a_scores, hand, prob)].

    Side-outs score nothing, so the serve can cycle; the cycle is summed in
    closed form (cyc = chance a full round of both sides scores nothing).
    """
    ps, po = (p, 1.0 - p) if a_srv else (1.0 - p, p)  # server / receiver rally odds
    cyc = po ** full * ps ** full
    back = po ** (full - h + 1) * ps ** full / (1.0 - cyc)  # back to server, hand 1
    out = []
    for j in range(1, full + 1):
        mine = (po ** (j - h) * ps if j >= h else 0.0) + back * po ** (j - 1) * ps
        theirs = (po ** (full - h + 1) + back * po ** full) * ps ** (j - 1) * po
        out.append((a_srv, j, mine))
        out.append((not a_srv, j, theirs))
    return out


def outcome_probs(p: float, target: int, doubles: bool, a_serves: bool) -> dict:
    """{('W', L) | ('L', L) | ('Wd',) | ('Ld',): probability} for side A,
    whose chance of winning any rally is p."""
    full = 2 if doubles else 1
    close_at = target - 2
    mass: dict = {(0, 0, a_serves, full): 1.0}  # starting side: last hand only
    out: dict = {}
    close = 0.0
    for total in range(0, 2 * target):
        for key in [k for k in mass if k[0] + k[1] == total]:
            a, b, a_srv, h = key
            v = mass.pop(key)
            for scorer_a, hand, pr in _scorer_dist(p, full, a_srv, h):
                na, nb = (a + 1, b) if scorer_a else (a, b + 1)
                w = v * pr
                if na == target:
                    out[("W", nb)] = out.get(("W", nb), 0.0) + w
                elif nb == target:
                    out[("L", na)] = out.get(("L", na), 0.0) + w
                elif na >= close_at and nb >= close_at:
                    close += w
                else:
                    k2 = (na, nb, scorer_a, hand)
                    mass[k2] = mass.get(k2, 0.0) + w
    win = _race(p, DEUCE_RACE)
    out[("Wd",)] = close * win
    out[("Ld",)] = close * (1.0 - win)
    return out


@lru_cache(maxsize=None)
def _table(target: int, doubles: bool, a_serves: bool):
    """Outcome probabilities on a p-grid (index i -> p = i / GRID)."""
    return [outcome_probs(min(max(i / GRID, 1e-6), 1 - 1e-6), target, doubles, a_serves)
            for i in range(GRID + 1)]


def _prob_and_slope(p: float, target: int, doubles: bool, a_serves, outcome):
    """(P(outcome), dP/dp) by interpolation; a_serves=None averages both servers."""
    serves = (True, False) if a_serves is None else (a_serves,)
    x = min(max(p, 0.0), 1.0) * GRID
    i = min(int(x), GRID - 1)
    P = dP = 0.0
    for s in serves:
        t = _table(target, doubles, s)
        lo, hi = t[i].get(outcome, 0.0), t[i + 1].get(outcome, 0.0)
        P += lo + (hi - lo) * (x - i)
        dP += (hi - lo) * GRID
    return P / len(serves), dP / len(serves)


@lru_cache(maxsize=None)
def _fisher_row(target: int, doubles: bool, a_serves, i: int) -> float:
    """Expected information about p from one game, at grid point i."""
    p = (i + 0.5) / GRID
    keys = set()
    for s in ((True, False) if a_serves is None else (a_serves,)):
        keys |= set(_table(target, doubles, s)[i])
    info = 0.0
    for k in keys:
        P, dP = _prob_and_slope(p, target, doubles, a_serves, k)
        if P > 1e-12:
            info += dP * dP / P
    return info


def _outcome(s1: int, s2: int):
    """Game score -> (target, outcome for side 1), or None if not a full game."""
    w, l = max(s1, s2), min(s1, s2)
    target = target_of(w)
    if target is None or s1 == s2:
        return None
    if w == target and l <= target - 3:
        return target, (("W", l) if s1 > s2 else ("L", l))
    return target, (("Wd",) if s1 > s2 else ("Ld",))


def game_terms(p: float, games, doubles: bool):
    """(d log P / dp, Fisher info) summed over the match's games, for side 1
    with rally probability p — or None if any game isn't a full side-out game."""
    parsed = [_outcome(a, b) for a, b in games]
    if not parsed or any(x is None for x in parsed):
        return None
    grad = info = 0.0
    a_serves = None  # game 1: first server unknown
    i = min(int(min(max(p, 0.0), 1.0) * GRID), GRID - 1)
    for (target, oc), (s1, s2) in zip(parsed, games):
        P, dP = _prob_and_slope(p, target, doubles, a_serves, oc)
        grad += dP / max(P, 1e-12)
        info += _fisher_row(target, doubles, a_serves, i)
        a_serves = s1 > s2  # the game's winner serves first in the next
    return grad, info
