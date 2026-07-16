"""Chronological driver over plain match records (PRD §7.7) — Phase 2.

STUB. Deterministic: processes matches in (match_time_utc, round_order,
match_id) order so `rate --rebuild` reproduces ratings exactly. Skips
rating_excluded matches (walkovers/no-play). Returns the final rating table plus
the per-match history. No Django imports — `manage.py rate` feeds it dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .types import MatchRecord, Rating, RatingConfig, RatingDelta


def match_sort_key(m: MatchRecord):
    """Deterministic ordering key (PRD §7.7)."""
    from datetime import datetime, timezone

    ts = m.match_time_utc or datetime.min.replace(tzinfo=timezone.utc)
    return (ts, m.round_order, m.match_id)


@dataclass
class RunResult:
    ratings: dict[tuple[int, str], Rating] = field(default_factory=dict)
    history: list[RatingDelta] = field(default_factory=list)


def run(matches: list[MatchRecord], config: RatingConfig) -> RunResult:
    """Process matches chronologically and return final ratings + history.

    Phase 2 — implemented once M1 ingestion acceptance passes.
    """
    raise NotImplementedError("rating.run is Phase 2 (post-M1)")
