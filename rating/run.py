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
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone

from collections import defaultdict

from .engine import update_period
from .seeding import cross_discipline_seed, flat_seed, rank_seed
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
    # Undo log for incremental re-rating: tournament_id -> {key: the key's
    # Rating just before that period (None = first seen there)}. Recorded only
    # for periods starting on/after `undo_since`.
    undo: dict[int, dict[tuple[int, str], Rating | None]] = field(default_factory=dict)


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


SeedRank = int | tuple[int, date | None]


def _usable_rank(seed, period_start: datetime | None) -> int | None:
    """The seed rank if it was KNOWN by `period_start`, else None.

    A bare int is trusted as-is (callers that already filtered). A
    (rank, observed_date) pair is used only when observed on/before the period
    start — a ranking earned years after a player's debut must not seed it
    (that leaks the future into history and inflates backtests).
    """
    if seed is None:
        return None
    if isinstance(seed, int):
        return seed
    rank, observed = seed
    if observed is None or period_start is None:
        return None
    return rank if observed <= period_start.date() else None


def period_sort_key(period: list[MatchRecord]):
    """A rating period's place in time: its earliest match's sort key."""
    return min(match_sort_key(x) for x in period)


def group_periods(matches: list[MatchRecord]) -> list[tuple[int, list[MatchRecord]]]:
    """Rateable matches grouped into rating periods (tournaments), in the
    deterministic order `run` processes them: [(tournament_id, matches)]."""
    periods: dict[int, list[MatchRecord]] = defaultdict(list)
    for m in matches:
        if m.rating_excluded or m.winner_side not in (1, 2):
            continue
        if not m.side1_player_ids or not m.side2_player_ids:
            continue
        periods[m.tournament_id].append(m)
    return sorted(periods.items(), key=lambda kv: period_sort_key(kv[1]))


def run(
    matches: list[MatchRecord],
    config: RatingConfig,
    seed_ranks: dict[tuple[int, str], SeedRank] | None = None,
    initial: dict[tuple[int, str], Rating] | None = None,
    undo_since: datetime | None = None,
) -> RunResult:
    """Process tournaments (rating periods) chronologically (PRD §7.7).

    Each tournament is a rating period: a player's rating is frozen at the
    period start (after inactivity inflation), all their matches in the
    tournament are rated against those frozen ratings, and the accumulated
    update is applied once at period end (`engine.update_period`). This is the
    tournament-locked model — meeting an opponent uses both sides' start-of-
    tournament strength, not a figure inflated by earlier-round wins.

    `seed_ranks` maps (player_id, event) -> BWF World Ranking, either a bare
    rank or (rank, observed_date). A new key is seeded from a rank only if it
    was observed by the start of the player's first period (PRD §7.6), else
    flat.

    `initial` resumes from earlier ratings (incremental rating): `matches`
    must then hold only periods that come after everything those ratings
    already include. The inputs are copied, never mutated, and the result is
    identical to a full run over all periods.

    `undo_since` records, for every period starting on/after it, each touched
    rating's state before the period (`RunResult.undo`) — what a later run
    needs to roll those periods back and replay them (see `rollback`).
    """
    result = RunResult()
    ratings = result.ratings
    seed_ranks = seed_ranks or {}

    events_of: dict[int, list[str]] = defaultdict(list)  # player -> rated events
    for (pid, event), r in (initial or {}).items():
        ratings[(pid, event)] = replace(r)
        events_of[pid].append(event)

    def rating_for(player_id: int, event: str, period_start) -> Rating:
        key = (player_id, event)
        r = ratings.get(key)
        if r is None:
            rank = _usable_rank(seed_ranks.get(key), period_start)
            if rank:
                r = rank_seed(rank, config)
            else:
                # Sorted, so the prior sums in the same order whether the run
                # is full or resumed (bit-identical results).
                others = [ratings[(player_id, e)] for e in sorted(events_of[player_id])]
                r = cross_discipline_seed(others, config) or flat_seed(config)
            ratings[key] = r
            events_of[player_id].append(event)
        return r

    for tid, period in group_periods(matches):
        period_start = min(
            (m.match_time_utc for m in period if m.match_time_utc),
            default=None,
        )
        if undo_since is not None and period_start is not None and period_start >= undo_since:
            log = result.undo[tid] = {}
            for m in period:
                for pid in (*m.side1_player_ids, *m.side2_player_ids):
                    key = (pid, m.event)
                    if key not in log:
                        prior = ratings.get(key)
                        log[key] = replace(prior) if prior is not None else None
        # Seed newcomers and inflate for inactivity ONCE, at the period start,
        # so every match in the tournament sees the same frozen rating.
        seen: set[tuple[int, str]] = set()
        for m in period:
            for pid in (*m.side1_player_ids, *m.side2_player_ids):
                key = (pid, m.event)
                if key in seen:
                    continue
                seen.add(key)
                _inflate_for_inactivity(
                    rating_for(pid, m.event, period_start), period_start, config
                )

        result.history.extend(update_period(period, ratings, config))

    return result


def rollback(
    ratings: dict[tuple[int, str], Rating],
    undo_logs: list[dict[tuple[int, str], Rating | None]],
) -> dict[tuple[int, str], Rating]:
    """Undo periods from current `ratings`, newest first.

    `undo_logs` are the periods' undo logs (RunResult.undo values) in
    processing order; they are applied in reverse. A key first seen in an
    undone period is removed. Returns a new dict; inputs are not mutated.
    """
    out = {k: replace(r) for k, r in ratings.items()}
    for log in reversed(undo_logs):
        for key, prior in log.items():
            if prior is None:
                out.pop(key, None)
            else:
                out[key] = replace(prior)
    return out
