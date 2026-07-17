"""Chronological driver over plain match records (PRD §7.7) — pure.

Deterministic: matches are processed in (match_time_utc, round_order, match_id)
order, so `rate --rebuild` reproduces ratings exactly. Ratings are keyed by
(player_id, event) — a player holds independent ratings per discipline. New
keys are seeded flat (PRD §7.6). Before each match a player's rd is re-inflated
for inactivity (PRD §7.4); excluded/undecided matches are skipped.

No Django imports — `manage.py rate` feeds this dataclasses and writes the
result back.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .engine import update_match
from .seeding import flat_seed
from .types import MatchRecord, Rating, RatingConfig, RatingDelta

# One "rating period" for inactivity inflation, in days (~a month of tour play).
_INFLATE_PERIOD_DAYS = 30.0
_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


def match_sort_key(m: MatchRecord):
    """Deterministic ordering key (PRD §7.7)."""
    return (m.match_time_utc or _MIN_TS, m.round_order, m.match_id)


@dataclass
class RunResult:
    ratings: dict[tuple[int, str], Rating] = field(default_factory=dict)
    history: list[RatingDelta] = field(default_factory=list)


def _inflate_for_inactivity(
    r: Rating, now: datetime | None, config: RatingConfig
) -> None:
    """Grow rd toward rd_init based on idle time since the last match (PRD §7.4).

    rd' = min(sqrt(rd² + c²·periods), rd_init), periods = idle_days / 30.
    A player with no prior match or no timestamp is left unchanged.
    """
    if r.last_match_utc is None or now is None or config.rd_inflate_c <= 0:
        return
    idle_days = (now - r.last_match_utc).total_seconds() / 86400.0
    if idle_days <= 0:
        return
    periods = idle_days / _INFLATE_PERIOD_DAYS
    inflated = math.sqrt(r.rd * r.rd + config.rd_inflate_c * config.rd_inflate_c * periods)
    r.rd = min(inflated, config.rd_init)


def run(matches: list[MatchRecord], config: RatingConfig) -> RunResult:
    """Process matches chronologically; return final ratings + per-match history."""
    result = RunResult()
    ratings = result.ratings

    def rating_for(player_id: int, event: str) -> Rating:
        key = (player_id, event)
        r = ratings.get(key)
        if r is None:
            r = flat_seed(config)
            ratings[key] = r
        return r

    for match in sorted(matches, key=match_sort_key):
        if match.rating_excluded or match.winner_side not in (1, 2):
            continue

        side1 = [rating_for(pid, match.event) for pid in match.side1_player_ids]
        side2 = [rating_for(pid, match.event) for pid in match.side2_player_ids]
        if not side1 or not side2:
            continue

        for r in (*side1, *side2):
            _inflate_for_inactivity(r, match.match_time_utc, config)

        result.history.extend(update_match(match, side1, side2, config))

    return result
