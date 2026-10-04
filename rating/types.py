"""Plain dataclasses the engine consumes and emits (PRD §7).

Framework-free by design: `manage.py rate` maps ORM rows to these on the way in
and back to rows on the way out. No Django imports here, ever.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class GameRecord:
    game_no: int
    side1_points: int
    side2_points: int


@dataclass(frozen=True)
class MatchRecord:
    """One normalized match handed to the engine, already ordered upstream."""

    match_id: int
    event: str  # discipline bucket MS/WS/MD/WD/XD
    match_time_utc: datetime | None
    round_order: int
    winner_side: int  # 1 or 2 — who advanced
    score_status: str  # Normal / Retired / Walkover / …
    scoring_format: str
    rating_excluded: bool
    side1_player_ids: tuple[int, ...]
    side2_player_ids: tuple[int, ...]
    games: tuple[GameRecord, ...] = field(default_factory=tuple)
    # Tier multiplier (W_tier) resolved by the bridge from settings; 1.0 = no
    # weighting. The engine never parses tier strings itself.
    tier_weight: float = 1.0
    # Rating-period key: all matches of a tournament are rated together against
    # start-of-period ratings (tournament-locked model). 0 = ungrouped.
    tournament_id: int = 0

    @property
    def is_retired(self) -> bool:
        return self.score_status.strip().lower() == "retired"


@dataclass
class Rating:
    """A single (player, event) rating with uncertainty (Glicko-2 style)."""

    mu: float
    rd: float
    sigma: float
    matches_played: int = 0
    last_match_utc: datetime | None = None


@dataclass(frozen=True)
class RatingConfig:
    """Engine constants, passed IN from Django settings (PRD §8).

    The engine never reads Django settings itself — this is the whole config
    surface it sees.
    """

    mu_init: float = 1500.0
    rd_init: float = 350.0
    sigma_init: float = 0.06
    tau: float = 0.5
    pair_blend: str = "mean"
    lambda_: float = 2.0
    m_min: float = 0.4
    m_max: float = 2.5
    d_floor: float = 0.0
    k_retire: float = 0.3
    rd_inflate_c: float = 34.6
    tier_weights: dict[str, float] = field(default_factory=dict)
    # Rank-based seeding (PRD §7.6): a new (player, event) with a known BWF World
    # Ranking is seeded on a log curve — rank 1 -> seed_rank_top_mu, rank
    # seed_rank_base (and beyond) -> mu_init — with a deliberately HIGH rd
    # (seed_rd) so the prior converges quickly to actual results.
    seed_rank_top_mu: float = 2300.0
    seed_rank_base: int = 400
    seed_rd: float = 300.0
    # Cross-discipline prior (PRD §7.6): a new (player, event) with no usable
    # rank seed starts from the player's strength in their OTHER disciplines,
    # partially pooled toward mu_init: mu = mu_init + w·(mean_other − mu_init),
    # rd = cross_prior_rd. Only ratings with >= cross_prior_min_matches count.
    # w = 0 disables it (flat seed).
    cross_prior_weight: float = 0.0
    cross_prior_rd: float = 250.0
    cross_prior_min_matches: int = 5
    # Which likelihood rates a period: "glicko" (binary result × margin
    # multiplier, engine.update_period) or "points" (rally-level model,
    # rating.points; rally_beta = rally-level slope, rally_weight = weight
    # per rally since rallies aren't independent).
    engine: str = "glicko"
    rally_beta: float = 0.13
    rally_weight: float = 0.35


@dataclass(frozen=True)
class RatingDelta:
    """One player's movement from a single match — becomes RatingHistory."""

    player_id: int
    event: str
    match_id: int
    mu_before: float
    mu_after: float
    rd_before: float
    rd_after: float
    delta: float
    applied_utc: datetime | None
