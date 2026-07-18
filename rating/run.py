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

from collections import defaultdict

from .engine import update_period
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
    """Process tournaments (rating periods) chronologically (PRD §7.7).

    Each tournament is a rating period: a player's rating is frozen at the
    period start (after inactivity inflation), all their matches in the
    tournament are rated against those frozen ratings, and the accumulated
    update is applied once at period end (`engine.update_period`). This is the
    tournament-locked model — meeting an opponent uses both sides' start-of-
    tournament strength, not a figure inflated by earlier-round wins.
    """
    result = RunResult()
    ratings = result.ratings

    def rating_for(player_id: int, event: str) -> Rating:
        key = (player_id, event)
        r = ratings.get(key)
        if r is None:
            r = flat_seed(config)
            ratings[key] = r
        return r

    # Group into rating periods (tournaments), ordered by their earliest match.
    periods: dict[int, list[MatchRecord]] = defaultdict(list)
    for m in matches:
        if m.rating_excluded or m.winner_side not in (1, 2):
            continue
        if not m.side1_player_ids or not m.side2_player_ids:
            continue
        periods[m.tournament_id].append(m)

    ordered = sorted(
        periods.values(), key=lambda ms: min(match_sort_key(x) for x in ms)
    )

    for period in ordered:
        period_start = min(
            (m.match_time_utc for m in period if m.match_time_utc),
            default=None,
        )
        # Seed newcomers and inflate for inactivity ONCE, at the period start,
        # so every match in the tournament sees the same frozen rating.
        seen: set[tuple[int, str]] = set()
        for m in period:
            for pid in (*m.side1_player_ids, *m.side2_player_ids):
                key = (pid, m.event)
                if key in seen:
                    continue
                seen.add(key)
                _inflate_for_inactivity(rating_for(pid, m.event), period_start, config)

        result.history.extend(update_period(period, ratings, config))

    return result
