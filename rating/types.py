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
    lambda_: float = 0.5
    m_min: float = 0.7
    m_max: float = 1.4
    d_floor: float = 0.50
    k_retire: float = 0.3
    rd_inflate_c: float = 34.6
    tier_weights: dict[str, float] = field(default_factory=dict)


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
