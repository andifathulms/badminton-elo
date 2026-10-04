"""Ranking-board rules shared by `rate`, `build_movement` and the API.

The default CURRENT board for a discipline: players with >= BOARD_MIN_MATCHES
rated matches who played within ACTIVE_DAYS of the latest match in the data,
ranked by the conservative rating mu − 2·rd. Ties break by player id so ranks
are deterministic. XD also has per-gender boards.
"""
from __future__ import annotations

from collections import defaultdict

ACTIVE_DAYS = 365  # idle longer than this counts as retired (current boards)
BOARD_MIN_MATCHES = 5
FORM_POINTS = 20  # tournament-start ratings kept for the form sparkline


def rank_entries(entries) -> dict:
    """[(key, value)] -> {key: 1-based rank}, highest value first, ties by key."""
    ordered = sorted(entries, key=lambda e: (-e[1], e[0]))
    return {k: i + 1 for i, (k, _) in enumerate(ordered)}


def board_ranks(rows) -> tuple[dict, dict]:
    """rows: [(player_id, gender, rating)] already filtered to the board.

    Returns ({player_id: overall rank}, {player_id: rank within gender}).
    """
    overall = rank_entries([(p, v) for p, _, v in rows])
    by_gender = defaultdict(list)
    for p, g, v in rows:
        if g:
            by_gender[g].append((p, v))
    within = {}
    for entries in by_gender.values():
        within.update(rank_entries(entries))
    return overall, within
