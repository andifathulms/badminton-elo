"""Candidate engine: a rally-level ("points-based") rating model. Pure.

Instead of a binary result scaled by a hand-tuned margin multiplier, the
rating gap sets the chance of winning ONE rally:

    p = σ(β · g(φ_opp) · (µ_side − µ_opp))          (Glicko-2 internal scale)

and game/match odds follow from badminton's actual scoring (race to 21, win
by 2, capped at 30; best of three). Each match updates ratings by the rallies
each side actually won — its likelihood is w·[n₁·log p + n₂·log(1−p)], where
w < 1 discounts rallies for not being independent. Matches without usable
rally points (side-out eras, retirements, no score) update on the match
result through the same model: P(win) = match(game(p)).

The update is Glicko's — one Newton step with each player's own uncertainty
— so seeding, the cross-discipline prior, inactivity inflation and the
tournament-locked periods are the same as the production engine
(`rating.run(update=...)`). Only the likelihood differs.

Ships only if it beats the Glicko-2 engine on held-out log-loss
(`manage.py backtest --engine points`).
"""
from __future__ import annotations

import math
from collections import defaultdict
from functools import lru_cache

from .engine import _SCALE, _g
from .types import MatchRecord, Rating, RatingConfig, RatingDelta

# Rally-point formats: (points to win a game, cap, games to win the match).
RALLY_FORMATS = {"3x21": (21, 30, 2), "3x15": (15, 21, 2), "3x11": (11, 15, 2)}
_DEFAULT_FORMAT = (21, 30, 2)


def game_win_prob(p: float, target: int = 21, cap: int = 30) -> float:
    """P(win a rally-scored game) given P(win a rally) = p."""
    q = 1.0 - p
    # Win target-k for k = 0 .. target-2 (opponent never reaches target-1 tie).
    win = sum(math.comb(target - 1 + k, k) * p**target * q**k for k in range(target - 1))
    # Reach (target-1)-all, then win by two, or by the next rally at cap-1 all.
    tie = math.comb(2 * (target - 1), target - 1) * (p * q) ** (target - 1)
    # From (target-1)-all a split rally moves the tie up one; ties from
    # target-1 to cap-2 need a two-rally lead, at (cap-1)-all the next rally wins.
    extra = cap - target
    deuce = sum((2 * p * q) ** j * p * p for j in range(extra)) + (2 * p * q) ** extra * p
    return win + tie * deuce


def match_win_prob(p: float, fmt: tuple[int, int, int] = _DEFAULT_FORMAT) -> float:
    """P(win the match) given P(win a rally) = p."""
    target, cap, need = fmt
    g = game_win_prob(p, target, cap)
    if need == 2:
        return g * g * (3.0 - 2.0 * g)
    # General best-of-(2·need−1).
    return sum(math.comb(need - 1 + k, k) * g**need * (1 - g) ** k for k in range(need))


@lru_cache(maxsize=None)
def _match_curve(fmt: tuple[int, int, int]):
    """match_win_prob on a fine grid of p, for fast lookups + derivatives."""
    n = 4000
    return [match_win_prob(i / n, fmt) for i in range(n + 1)]


def _match_and_slope(p: float, fmt) -> tuple[float, float]:
    """(P(match), dP/dp) by linear interpolation on the cached curve."""
    curve = _match_curve(fmt)
    n = len(curve) - 1
    x = min(max(p, 0.0), 1.0) * n
    i = min(int(x), n - 1)
    lo, hi = curve[i], curve[i + 1]
    return lo + (hi - lo) * (x - i), (hi - lo) * n


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _fmt(m: MatchRecord):
    return RALLY_FORMATS.get(m.scoring_format, _DEFAULT_FORMAT)


def make_update(beta: float, rally_weight: float):
    """A period update (same contract as engine.update_period) for this model."""

    def update_period(matches, ratings, config: RatingConfig) -> list[RatingDelta]:
        frozen = {k: (r.mu, r.rd) for k, r in ratings.items()}

        def team(pids, event):
            n = len(pids)
            mu = sum(frozen[(p, event)][0] for p in pids) / n
            rd = math.sqrt(sum(frozen[(p, event)][1] ** 2 for p in pids) / n)
            return (mu - 1500.0) / _SCALE, rd / _SCALE

        acc = defaultdict(lambda: {"grad": 0.0, "info": 0.0, "n": 0, "last": None, "contribs": []})
        for m in sorted(matches, key=lambda x: (x.round_order, x.match_id)):
            if m.rating_excluded or m.winner_side not in (1, 2):
                continue
            if not m.side1_player_ids or not m.side2_player_ids:
                continue
            mu1, phi1 = team(m.side1_player_ids, m.event)
            mu2, phi2 = team(m.side2_player_ids, m.event)
            n1 = sum(g.side1_points for g in m.games)
            n2 = sum(g.side2_points for g in m.games)
            rally = (m.scoring_format in RALLY_FORMATS and not m.is_retired and n1 + n2 > 0)
            fmt = _fmt(m)
            for ids, won, n_s, mu_t, mu_o, phi_o in (
                (m.side1_player_ids, m.winner_side == 1, n1, mu1, mu2, phi2),
                (m.side2_player_ids, m.winner_side == 2, n2, mu2, mu1, phi1),
            ):
                gg = _g(phi_o)
                p = _sigmoid(beta * gg * (mu_t - mu_o))
                slope = beta * gg * p * (1.0 - p)  # dp/dµ
                if rally:
                    total = n1 + n2
                    grad = rally_weight * beta * gg * (n_s - total * p)
                    info = rally_weight * total * beta * gg * slope
                else:
                    P, dP = _match_and_slope(p, fmt)
                    P = min(max(P, 1e-9), 1 - 1e-9)
                    dmu = dP * slope
                    wt = config.k_retire if m.is_retired else 1.0
                    grad = wt * ((1.0 if won else 0.0) - P) / (P * (1.0 - P)) * dmu
                    info = wt * dmu * dmu / (P * (1.0 - P))
                for pid in ids:
                    a = acc[(pid, m.event)]
                    a["grad"] += grad
                    a["info"] += info
                    a["n"] += 1
                    a["contribs"].append((m, grad))
                    if m.match_time_utc and (a["last"] is None or m.match_time_utc > a["last"]):
                        a["last"] = m.match_time_utc

        deltas: list[RatingDelta] = []
        for (pid, event), a in acc.items():
            r: Rating = ratings[(pid, event)]
            mu = (r.mu - 1500.0) / _SCALE
            phi = r.rd / _SCALE
            phi_star2 = phi * phi + r.sigma * r.sigma
            var = 1.0 / (1.0 / phi_star2 + a["info"])
            mu_before, rd_before = r.mu, r.rd
            r.mu = (mu + var * a["grad"]) * _SCALE + 1500.0
            r.rd = min(math.sqrt(var) * _SCALE, config.rd_init)
            r.matches_played += a["n"]
            r.last_match_utc = a["last"] or r.last_match_utc
            cum = 0.0
            for m, grad in a["contribs"]:
                d_pts = var * grad * _SCALE
                cum += d_pts
                deltas.append(RatingDelta(
                    player_id=pid, event=event, match_id=m.match_id,
                    mu_before=mu_before, mu_after=mu_before + cum,
                    rd_before=rd_before, rd_after=r.rd, delta=d_pts,
                    applied_utc=m.match_time_utc,
                ))
        return deltas

    return update_period


def make_predictor(beta: float, fmt: tuple[int, int, int] = _DEFAULT_FORMAT):
    """P(side 1 wins the match) from two (mu, rd) sides — symmetric."""

    def win_probability(mu1, rd1, mu2, rd2):
        phi = math.sqrt(rd1 * rd1 + rd2 * rd2) / _SCALE
        p = _sigmoid(beta * _g(phi) * (mu1 - mu2) / _SCALE)
        return _match_and_slope(p, fmt)[0]

    return win_probability
