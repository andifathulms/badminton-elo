"""Pure rating engine (PRD §7) — NO Django, NO ORM, NO request cycle.

This package takes plain dataclasses/dicts in and returns rating rows out. The
ONLY bridge to persistence is `manage.py rate`, which reads ORM rows, converts
them to the dataclasses in `rating.types`, calls `rating.run`, and writes the
results back. Keeping this boundary is non-negotiable (CLAUDE.md architecture
principle): it is what keeps the rating math unit-testable and uncorrupted.

Phase 2 is implemented: the Glicko-2-with-pairs update (§7.1–§7.5), the
dominance/margin math (§7.3), and the deterministic chronological driver (§7.7).
`manage.py rate` is the only bridge to persistence.
"""
from .dominance import dominance, margin_multiplier
from .engine import update_match, update_period
from .run import RunResult, match_sort_key, run
from .types import (
    GameRecord,
    MatchRecord,
    Rating,
    RatingConfig,
    RatingDelta,
)

__all__ = [
    "dominance",
    "margin_multiplier",
    "update_match",
    "update_period",
    "run",
    "RunResult",
    "match_sort_key",
    "GameRecord",
    "MatchRecord",
    "Rating",
    "RatingConfig",
    "RatingDelta",
]
