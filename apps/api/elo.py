"""In-tournament cumulative ELO for display.

The rating engine is tournament-locked: every match in a tournament is scored
against the player's rating at the START of that tournament, so RatingHistory
stores the SAME `mu_before` for each match and `mu_after = mu_before + delta`.

Showing that verbatim is misleading — the second win of a run reads as
"2382 -> 2400 (+18)" when the player was really already at ~2387 after the
first win. This helper rebuilds a running before/after within each tournament
(and discipline) by accumulating the per-match deltas in bracket order, so the
displayed figures chain correctly while the underlying (locked) maths is
untouched.
"""
from __future__ import annotations

from apps.ingest.models import RatingHistory


def cumulative_elo(player_id: int, tournament_id: int) -> dict[int, tuple[float, float, float]]:
    """{match_id: (before, after, delta)} with before/after chained per event."""
    rows = list(
        RatingHistory.objects.filter(
            player_id=player_id, match__tournament_id=tournament_id
        )
        .select_related("match")
        .order_by("event", "match__round_order", "match__match_time_utc", "match_id")
    )
    out: dict[int, tuple[float, float, float]] = {}
    running: dict[str, float] = {}
    for h in rows:
        prev = running.get(h.event)
        before = h.mu_before if prev is None else prev
        after = before + h.delta
        running[h.event] = after
        out[h.match_id] = (before, after, h.delta)
    return out


def tournament_match_elo(tournament_id: int) -> dict[int, dict[int, tuple]]:
    """{match_id: {player_id: (before, after, delta)}} for a whole tournament,
    with before/after chained per (player, discipline). One query, cumulative."""
    rows = list(
        RatingHistory.objects.filter(match__tournament_id=tournament_id)
        .select_related("match")
        .order_by(
            "player_id", "event", "match__round_order", "match__match_time_utc", "match_id"
        )
    )
    out: dict[int, dict[int, tuple]] = {}
    running: dict[tuple, float] = {}
    for h in rows:
        key = (h.player_id, h.event)
        prev = running.get(key)
        before = h.mu_before if prev is None else prev
        after = before + h.delta
        running[key] = after
        out.setdefault(h.match_id, {})[h.player_id] = (before, after, h.delta)
    return out
