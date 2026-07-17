"""Shared h2h/match parsing — used by both the bulk `collect_h2h` command and
the on-demand statistics API endpoint."""
from __future__ import annotations

from django.utils import timezone

from .api import endpoints
from .api.client import BwfClient
from .models import Match, MatchStatistics


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_match_stats(raw: dict) -> dict | None:
    """h2h/match payload -> MatchStatistics field dict (None if not usable)."""
    if not isinstance(raw, dict) or "stats" not in raw:
        return None
    s = raw.get("stats") or {}
    progression = [
        [[_int(d.get("team1")), _int(d.get("team2"))]
         for d in (g.get("match_set_details_model") or [])]
        for g in (raw.get("games") or [])
    ]
    return {
        "team1_rallies_won": _int(s.get("team1_rallies_won")),
        "team1_rallies_played": _int(s.get("team1_rallies_played")),
        "team2_rallies_won": _int(s.get("team2_rallies_won")),
        "team2_rallies_played": _int(s.get("team2_rallies_played")),
        "team1_consecutive_points": _int(s.get("team1_consecutive_points")),
        "team2_consecutive_points": _int(s.get("team2_consecutive_points")),
        "team1_game_points": _int(s.get("team1_game_points")),
        "team2_game_points": _int(s.get("team2_game_points")),
        "duration_min": _int((raw.get("progress") or {}).get("duration")),
        "point_progression": progression or None,
        "fetched_utc": timezone.now(),
    }


def fetch_and_store_stats(match: Match, client: BwfClient | None = None) -> MatchStatistics | None:
    """Fetch h2h/match for `match`, store, and return the MatchStatistics row.

    Returns None if the match has no code or the payload is unusable.
    """
    if not match.code:
        return None
    own = client is None
    client = client or BwfClient()
    try:
        raw = client.get_json(endpoints.h2h_match(match.tournament_id, match.code))
    finally:
        if own:
            client.close()
    fields = parse_match_stats(raw)
    if fields is None:
        return None
    obj, _ = MatchStatistics.objects.update_or_create(match=match, defaults=fields)
    return obj
