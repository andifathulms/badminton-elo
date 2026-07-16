"""BWF fan-API endpoint builders — the single source of truth for URLs/params.

Framework-agnostic (stdlib only). Drops into either stack unchanged:
  - lean stack:   src/badminton_elo/api/endpoints.py
  - Django stack: apps/ingest/api/endpoints.py

CONFIRMED vs TO-CONFIRM
-----------------------
Only `day_matches` was captured with its full request URL (see the network-tab
screenshot). For every other endpoint the *response shape* is known (we have real
payloads) but the exact *request* path/param names are guesses. Each is marked
below and flagged in `CONFIRMED`. Confirm the guesses in one pass:

  1. Open the BWF tournament page, DevTools -> Network -> filter XHR/Fetch.
  2. Click through Matches / Draw / a match detail.
  3. For each call, copy the ":path" and query string from the Headers panel.
  4. Fix the corresponding function here. Because every URL is built in this one
     module, each correction is a one-line change and nothing else moves.

The vue-* calls may sit on a different host than day-matches (the fan pages use
bwfworldtour.bwfbadminton.com as referer and may proxy through a different base).
If so, set VUE_BASE separately — don't assume it equals BASE.
"""

from __future__ import annotations

from datetime import date as _date
from urllib.parse import urlencode

# --- hosts -------------------------------------------------------------------
# Confirmed from the day-matches request.
BASE = "https://extranet-lv.bwfbadminton.com/api"
# TO CONFIRM: the vue-* endpoints may live on this same base or a different one.
VUE_BASE = BASE

# Which builders are verified against a real captured request URL.
CONFIRMED = {
    "day_matches": True,
    "vue_tournament_detail": False,
    "vue_tournament_draws": False,
    "vue_tournament_draw_data": False,
    "players": False,
    "match_statistics": False,
}


def _url(base: str, path: str, **params) -> str:
    """Join base + path and append non-None query params, stably ordered."""
    clean = {k: v for k, v in params.items() if v is not None}
    qs = urlencode(clean)
    url = f"{base}/{path.lstrip('/')}"
    return f"{url}?{qs}" if qs else url


def _fmt_date(d: str | _date) -> str:
    return d.isoformat() if isinstance(d, _date) else d


# --- CONFIRMED ---------------------------------------------------------------

def day_matches(tournament_code: str, date: str | _date) -> str:
    """All matches on one date across all disciplines.

    CONFIRMED — captured URL:
      .../api/tournaments/day-matches?tournamentCode=...&date=YYYY-MM-DD&order=2&court=0
    Requires iterating dates from tournament start_date..end_date.
    """
    return _url(
        BASE, "tournaments/day-matches",
        tournamentCode=tournament_code,
        date=_fmt_date(date),
        order=2,
        court=0,
    )


# --- TO CONFIRM (response shapes known; request params are best guesses) ------

def vue_tournament_detail(tournament_code: str) -> str:
    """Tournament metadata (id, name, dates, categoryModel.name = tier, ...).

    TO CONFIRM param name — guess: tournamentCode. Could also be keyed by numeric id.
    """
    return _url(VUE_BASE, "tournaments/vue-tournament-detail",
                tournamentCode=tournament_code)


def vue_tournament_draws(tournament_code: str) -> str:
    """List of draws in a tournament (results[]: value, text=MS/WS/MD/WD/XD,
    doubles, qualification, stage_name, size, ...). Filter qualification==0 for main draw.

    TO CONFIRM param name — guess: tournamentCode.
    """
    return _url(VUE_BASE, "tournaments/vue-tournament-draws",
                tournamentCode=tournament_code)


def vue_tournament_draw_data(tournament_code: str, draw_value: str | int) -> str:
    """PRIMARY results source: full bracket for one draw, incl. a flat `matches`
    array with every match (all rounds), game-by-game scores, player ids, status.

    TO CONFIRM the draw param name. `draw_value` is the `value` from
    vue_tournament_draws (e.g. "10" for XD main). The param key is one of:
    draw / drawId / drawCode / value — verify in the network tab.
    """
    return _url(VUE_BASE, "tournaments/vue-tournament-draw-data",
                tournamentCode=tournament_code,
                draw=draw_value)  # TO CONFIRM key: draw | drawId | drawCode | value


def players(tournament_code: str) -> str:
    """Player directory for a tournament (supplementary — players are also
    discoverable from match payloads).

    TO CONFIRM param name — guess: tournamentCode.
    """
    return _url(VUE_BASE, "tournaments/players",
                tournamentCode=tournament_code)


def match_statistics(match_id: str | int) -> str:
    """Per-match detail: rally stats, per-game progress, embedded BWF rankings
    (for rank-based seeding), career stats, player dob/height. OPTIONAL in Phase 1.

    TO CONFIRM host, path, and key. Likely keyed by match id; may live on a
    different service (bwfworldtour.*). Guess only.
    """
    return _url(VUE_BASE, "tournaments/match-statistics",
                matchId=match_id)  # TO CONFIRM path + key


# --- convenience -------------------------------------------------------------

def unconfirmed() -> list[str]:
    """Names of builders still using guessed request params — warn/log on first use."""
    return [name for name, ok in CONFIRMED.items() if not ok]


if __name__ == "__main__":
    code = "71AC3AB2-C072-444C-B479-4AC73C756C14"  # Malaysia Masters 2026
    print("CONFIRMED:")
    print(" ", day_matches(code, "2026-05-24"))
    print("TO CONFIRM (guessed params):")
    print(" ", vue_tournament_detail(code))
    print(" ", vue_tournament_draws(code))
    print(" ", vue_tournament_draw_data(code, "10"))  # XD main draw
    print(" ", players(code))
    print(" ", match_statistics(1518158))
    print("\nStill unconfirmed:", unconfirmed())
