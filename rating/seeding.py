"""Seeding & cold start (PRD §7.6) — Phase 2.

STUB. MVP seeds every (player, event) flat at (mu_init, rd_init); later a
rank-based seed maps BWF currentRank -> Elo via a percentile curve with HIGH rd
(priors, not truth). Doubles ranks are per-pair, so an individual is seeded from
their best/points-weighted partnership (SEED_DOUBLES_FROM).
"""
from __future__ import annotations

from .types import Rating, RatingConfig


def flat_seed(config: RatingConfig) -> Rating:
    """MVP cold-start seed — flat (mu_init, rd_init, sigma_init)."""
    return Rating(mu=config.mu_init, rd=config.rd_init, sigma=config.sigma_init)


def rank_seed(current_rank: int, config: RatingConfig) -> Rating:
    """Rank-based seed via percentile -> Elo curve. Phase 2."""
    raise NotImplementedError("rating.seeding.rank_seed is Phase 2 (post-M1)")
