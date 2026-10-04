"""Read-side win probability — pure, no state changes.

The single source of truth for "who is expected to win" wherever a prediction
is SHOWN or SCORED: the H2H page, the calibration diagram, upset ratings, and
the backtest harness. It never mutates a Rating.

Why it differs from the engine's update expectation: Glicko-2's update
(`engine._expected`) damps by the OPPONENT's φ only, because it asks "how
surprised should *this* player be". A displayed head-to-head must be symmetric
— P(A beats B) == 1 − P(B beats A) — so here g() uses the uncertainty of the
rating DIFFERENCE, sqrt(rd₁² + rd₂²). Both share the same scale and blend.

A side (singles or doubles) is blended like everywhere else: mu = mean of the
members, rd = RMS of the members (PRD §7.2).
"""
from __future__ import annotations

import math

SCALE = 173.7178  # Glicko-2 natural <-> internal scale (same as engine)


def team_rating(members) -> tuple[float, float] | None:
    """Blend (mu, rd) members into one side: mean mu, RMS rd. None if empty.

    Members with a missing mu or rd are ignored.
    """
    members = [(mu, rd) for mu, rd in members if mu is not None and rd is not None]
    if not members:
        return None
    mu = sum(mu for mu, _ in members) / len(members)
    rd = math.sqrt(sum(rd * rd for _, rd in members) / len(members))
    return mu, rd


def conservative(mu: float, rd: float) -> float:
    """The displayed 'rating': mu − 2·rd (a ~97.5% lower bound)."""
    return mu - 2.0 * rd


def win_probability(mu1: float, rd1: float, mu2: float, rd2: float) -> float:
    """P(side 1 beats side 2) in [0, 1], on the natural 1500/350 scale."""
    phi_diff = math.sqrt(rd1 * rd1 + rd2 * rd2) / SCALE
    g = 1.0 / math.sqrt(1.0 + 3.0 * phi_diff * phi_diff / (math.pi * math.pi))
    return 1.0 / (1.0 + math.exp(-g * (mu1 - mu2) / SCALE))
