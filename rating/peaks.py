"""All-time peak ratings from a history stream — pure.

The highest point of a noisy series runs high: a newcomer on a lucky streak
can post a peak while their rating is still a guess (rd ~ 200+). A peak only
counts once the rating is settled — rd_after <= max_rd. A player who never
settles falls back to their highest raw figure, so everyone has a peak.
"""
from __future__ import annotations

from typing import Iterable

from .types import RatingDelta

Peak = tuple[float, float, object]  # (mu, rd, when)


def peak_ratings(
    history: Iterable[RatingDelta],
    max_rd: float,
    start: dict[tuple[int, str], Peak] | None = None,
) -> dict[tuple[int, str], Peak]:
    """(player_id, event) -> (peak_mu, rd_at_peak, when).

    `start` carries peaks from an earlier run (incremental rating); they count
    as settled peaks. Settled peaks always beat unsettled ones.
    """
    settled: dict[tuple[int, str], Peak] = dict(start or {})
    raw: dict[tuple[int, str], Peak] = {}
    for d in history:
        key = (d.player_id, d.event)
        cand = (d.mu_after, d.rd_after, d.applied_utc)
        target = settled if d.rd_after <= max_rd else raw
        best = target.get(key)
        if best is None or cand[0] > best[0]:
            target[key] = cand
    return {**raw, **settled}
