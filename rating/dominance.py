"""Format-normalized dominance and margin multiplier (PRD §7.3).

Pure functions — the one part of the engine implemented before Phase 2 because
it is trivial, fully specified, and needed by the ingestion tests' sibling
checks. Dominance is computed for `Normal` matches ONLY; callers must not read
the scoreline for retirements/walkovers (CLAUDE.md domain rule 2).
"""
from __future__ import annotations

from .types import GameRecord, RatingConfig


def dominance(
    games: tuple[GameRecord, ...] | list[GameRecord],
    winner_side: int,
    *,
    d_floor: float = 0.0,
) -> float:
    """Return d = winner_points / total_points across the whole match.

    Comparable across 3x21 / 3x15 / 5x11 / side-out formats because it is a
    ratio, not a raw point difference. Floored at ``d_floor`` (default 0: a
    winner who scored fewer total points gets d < 0.5, so M < 1). Returns 0.5
    (neutral) if no points exist.
    """
    winner_pts = 0
    total_pts = 0
    for g in games:
        w = g.side1_points if winner_side == 1 else g.side2_points
        total_pts += g.side1_points + g.side2_points
        winner_pts += w
    if total_pts <= 0:
        return max(0.5, d_floor)
    return max(winner_pts / total_pts, d_floor)


def margin_multiplier(d: float, config: RatingConfig) -> float:
    """M = 1 + LAMBDA*(2d-1), clamped to [M_MIN, M_MAX] (PRD §7.3).

    Scales only the magnitude of a rating update; win/loss stays binary.
    """
    m = 1.0 + config.lambda_ * (2.0 * d - 1.0)
    return max(config.m_min, min(config.m_max, m))
