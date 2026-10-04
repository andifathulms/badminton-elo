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

Everything here is ONE query, whatever the number of players or tournaments.
"""
from __future__ import annotations

from apps.ingest.models import RatingHistory

Chain = tuple[float, float, float]  # (before, after, delta)


def chained_elo(
    tournament_ids, player_ids=None
) -> dict[int, dict[int, Chain]]:
    """{match_id: {player_id: (before, after, delta)}}, chained per
    (player, discipline, tournament) in bracket order. One query."""
    qs = RatingHistory.objects.filter(match__tournament_id__in=list(tournament_ids))
    if player_ids is not None:
        qs = qs.filter(player_id__in=list(player_ids))
    rows = qs.order_by(
        "player_id", "event", "match__tournament_id",
        "match__round_order", "match__match_time_utc", "match_id",
    ).values_list(
        "player_id", "event", "match__tournament_id", "match_id", "mu_before", "delta"
    )
    out: dict[int, dict[int, Chain]] = {}
    running: dict[tuple, float] = {}
    for pid, event, tid, mid, mu_before, delta in rows:
        key = (pid, event, tid)
        before = running.get(key, mu_before)
        after = before + delta
        running[key] = after
        out.setdefault(mid, {})[pid] = (before, after, delta)
    return out


def cumulative_elo(player_id: int, tournament_id: int) -> dict[int, Chain]:
    """{match_id: (before, after, delta)} for one player at one tournament."""
    return {
        mid: by_player[player_id]
        for mid, by_player in chained_elo([tournament_id], [player_id]).items()
    }


def tournament_match_elo(tournament_id: int) -> dict[int, dict[int, Chain]]:
    """{match_id: {player_id: (before, after, delta)}} for a whole tournament."""
    return chained_elo([tournament_id])
