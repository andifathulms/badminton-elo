"""Head-to-head win probability from stored ratings.

The pure engine (`rating/engine.py`) owns the Glicko-2 update; it must not be
imported into the serving layer (it mutates ratings). This is the *read-side*
mirror of its expectation formula (engine `_g`/`_expected`), used only to predict
a single matchup from two players' current (mu, rd) — no state is changed.

For a symmetric prediction the g() damping uses the uncertainty of the RATING
DIFFERENCE (sqrt(rd1² + rd2²)), so P(1 beats 2) == 1 − P(2 beats 1). A team
(doubles) is blended like everywhere else: mu = mean(members), rd = RMS(members).
"""
from __future__ import annotations

import math

_SCALE = 173.7178  # Glicko-2 natural<->internal scale (matches rating/engine.py)


def team_rating(members: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Blend (mu, rd) members into one side: mean mu, RMS rd. None if empty."""
    members = [(mu, rd) for mu, rd in members if mu is not None and rd is not None]
    if not members:
        return None
    mu = sum(mu for mu, _ in members) / len(members)
    rd = math.sqrt(sum(rd * rd for _, rd in members) / len(members))
    return mu, rd


def win_probability(mu1: float, rd1: float, mu2: float, rd2: float) -> float:
    """P(side 1 beats side 2) in [0,1], on the natural 1500/350 scale."""
    m1 = (mu1 - 1500.0) / _SCALE
    m2 = (mu2 - 1500.0) / _SCALE
    phi_diff = math.sqrt(rd1 * rd1 + rd2 * rd2) / _SCALE
    g = 1.0 / math.sqrt(1.0 + 3.0 * phi_diff * phi_diff / (math.pi * math.pi))
    return 1.0 / (1.0 + math.exp(-g * (m1 - m2)))
