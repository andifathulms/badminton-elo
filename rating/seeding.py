"""Seeding & cold start (PRD §7.6).

New (player, event) keys seed flat at (mu_init, rd_init) unless a BWF World
Ranking is known, in which case `rank_seed` maps the rank to a prior mu on a log
curve — with a HIGH rd so it is a prior, not a truth, and converges fast. For
doubles the pair rank is used for both members (the bridge supplies it).
"""
from __future__ import annotations

import math

from .types import Rating, RatingConfig


def flat_seed(config: RatingConfig) -> Rating:
    """MVP cold-start seed — flat (mu_init, rd_init, sigma_init)."""
    return Rating(mu=config.mu_init, rd=config.rd_init, sigma=config.sigma_init)


def rank_seed(current_rank: int | None, config: RatingConfig) -> Rating:
    """Seed from a BWF World Ranking (PRD §7.6).

    Log curve: rank 1 -> seed_rank_top_mu, rank seed_rank_base (and worse) ->
    mu_init. Uncertainty is high (seed_rd) so results quickly override the prior.
    Falls back to a flat seed for a missing/invalid rank.
    """
    if not current_rank or current_rank < 1:
        return flat_seed(config)
    base = config.seed_rank_base
    span = config.seed_rank_top_mu - config.mu_init
    slope = span / math.log(base)
    mu = config.mu_init + max(0.0, slope * (math.log(base) - math.log(current_rank)))
    mu = min(mu, config.seed_rank_top_mu)
    return Rating(mu=mu, rd=config.seed_rd, sigma=config.sigma_init)


def cross_discipline_seed(
    others: list[Rating], config: RatingConfig
) -> Rating | None:
    """Seed from the player's other disciplines (partial pooling), or None.

    `others` are the player's current ratings in other events. Each counts if
    it has >= cross_prior_min_matches; they are averaged with 1/rd² weights
    (settled ratings dominate) and shrunk toward mu_init by cross_prior_weight.
    """
    w = config.cross_prior_weight
    if w <= 0:
        return None
    usable = [r for r in others if r.matches_played >= config.cross_prior_min_matches]
    if not usable:
        return None
    weights = [1.0 / (r.rd * r.rd) for r in usable]
    mean = sum(r.mu * wt for r, wt in zip(usable, weights)) / sum(weights)
    mu = config.mu_init + w * (mean - config.mu_init)
    return Rating(mu=mu, rd=config.cross_prior_rd, sigma=config.sigma_init)
