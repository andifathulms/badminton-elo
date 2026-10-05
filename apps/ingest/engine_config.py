"""settings.RATING -> the pure engine's config, and the matching predictor.

The engine never reads Django settings (CLAUDE.md); this bridge is the one
place that turns them into a `rating.RatingConfig`. The read side (H2H,
calibration) uses `win_predictor()` so displayed win chances always come from
the same model that produced the ratings.
"""
from __future__ import annotations

from django.conf import settings

from rating import RatingConfig
from rating.predict import predictor_for


def rating_config(overrides: dict | None = None) -> RatingConfig:
    """settings.RATING -> RatingConfig. `overrides` (same keys) win, for backtests."""
    r = {**settings.RATING, **(overrides or {})}
    return RatingConfig(
        mu_init=r["MU_INIT"],
        rd_init=r["RD_INIT"],
        sigma_init=r["SIGMA_INIT"],
        tau=r["TAU"],
        pair_blend=r["PAIR_BLEND"],
        lambda_=r["LAMBDA"],
        m_min=r["M_MIN"],
        m_max=r["M_MAX"],
        d_floor=r["D_FLOOR"],
        k_retire=r["K_RETIRE"],
        rd_inflate_c=r["RD_INFLATE_C"],
        tier_weights=r["TIER_WEIGHTS"],
        seed_rank_top_mu=r["SEED_RANK_TOP_MU"],
        seed_rank_base=r["SEED_RANK_BASE"],
        seed_rd=r["SEED_RD"],
        cross_prior_weight=r.get("CROSS_PRIOR_WEIGHT", 0.0),
        cross_prior_rd=r.get("CROSS_PRIOR_RD", 250.0),
        cross_prior_min_matches=r.get("CROSS_PRIOR_MIN_MATCHES", 5),
        engine=r.get("ENGINE", "glicko"),
        rally_beta=r.get("RALLY_BETA", 0.13),
        rally_weight=r.get("RALLY_WEIGHT", 0.35),
        sideout_weight=r.get("SIDEOUT_WEIGHT", 0.0),
    )


def win_predictor():
    """P(side 1 wins) from (mu1, rd1, mu2, rd2) for the configured engine."""
    return predictor_for(rating_config())
