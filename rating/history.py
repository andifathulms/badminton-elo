"""History engine: TrueSkill Through Time smoothing for all-time comparisons.

The production engine is a filter — a rating at time t uses only results up
to t, which is right for "who is better now" but noisy for "how good was she
in 2015" or "who peaked highest". TrueSkill Through Time (Dangauthier et al.;
`trueskillthroughtime`) fits each discipline's whole timeline at once, so a
past estimate also uses later results.

Held-out check on men's singles (5% of matches hidden, skill estimated at
their dates): log-loss 0.4487 vs 0.5215 for the production engine. Used for
the all-time board and yearly skill curves, never for live ratings.

Pure: matches in, curves out. Scale: TTT skill differences are first mapped
onto the 1500 display scale with the production engine's win odds (TTT sums
partners' skills, so a doubles unit differs from singles), then calibrated
to the live ratings with `fit_scale` — TTT spreads a decades-long field much
wider, so raw numbers wouldn't be comparable with today's ratings.
"""
from __future__ import annotations

import math
from collections import defaultdict

import trueskillthroughtime as ttt

from .run import match_sort_key
from .types import MatchRecord

# A 1500-scale rating gap D gives odds Φ(D / 295.6) (logistic Glicko scale);
# TTT with n players a side gives Φ(Δ_sum / sqrt(2n)) for a gap of per-player
# skills averaging Δ (Δ_sum = nΔ). Equal odds -> points per TTT unit:
_GLICKO_PROBIT = 1.702 * 173.7178  # ≈ 295.6


def display_scale(players_per_side: int) -> float:
    n = players_per_side
    return _GLICKO_PROBIT * n / math.sqrt(2 * n)


def smooth(
    matches: list[MatchRecord],
    *,
    sigma: float = 1.6,
    gamma: float = 0.05,
    beta: float = 1.0,
    iterations: int = 6,
) -> dict[tuple[int, str], list[tuple[float, float, float]]]:
    """(player_id, event) -> [(day, mu, rd)] smoothed skill on the display
    scale, one point per day the player played. `day` = days since the epoch.

    Excluded, retired and undecided matches are skipped (a retirement says
    little about skill). Each discipline is fitted independently.
    """
    by_event: dict[str, list[MatchRecord]] = defaultdict(list)
    for m in matches:
        if (m.rating_excluded or m.is_retired or m.winner_side not in (1, 2)
                or not m.side1_player_ids or not m.side2_player_ids
                or m.match_time_utc is None):
            continue
        by_event[m.event].append(m)

    out: dict[tuple[int, str], list[tuple[float, float, float]]] = {}
    for event, ms in by_event.items():
        ms.sort(key=match_sort_key)
        per_side = max(max(len(m.side1_player_ids), len(m.side2_player_ids)) for m in ms)
        k = display_scale(per_side)
        h = ttt.History(
            [[[str(p) for p in m.side1_player_ids], [str(p) for p in m.side2_player_ids]]
             for m in ms],
            [[1, 0] if m.winner_side == 1 else [0, 1] for m in ms],
            [int(m.match_time_utc.timestamp() // 86400) for m in ms],
            sigma=sigma, gamma=gamma, beta=beta,
        )
        h.convergence(iterations=iterations, verbose=False)
        for pid, curve in h.learning_curves().items():
            out[(int(pid), event)] = [
                (t, 1500.0 + k * g.mu, k * g.sigma) for t, g in curve
            ]
    return out


def best_point(curve: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """The (day, mu, rd) where mu − 2·rd peaks: the all-time best, judged
    conservatively so a thinly-evidenced spike doesn't count."""
    return max(curve, key=lambda p: p[1] - 2.0 * p[2])


def fit_scale(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares line live ≈ a + b·smoothed over (smoothed, live) pairs.

    TTT spreads skills wider than the live engine (it fits decades at once),
    so smoothed numbers are mapped onto the live scale: same order, numbers a
    reader can compare with today's ratings. Identity if there's too little
    to fit.
    """
    n = len(pairs)
    if n < 2:
        return 0.0, 1.0
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    if sxx <= 0:
        return 0.0, 1.0
    b = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    return my - b * mx, b


def rescale(curve, a: float, b: float):
    """Apply live ≈ a + b·smoothed to a curve's (day, mu, rd) points."""
    return [(day, a + b * mu, b * rd) for day, mu, rd in curve]
