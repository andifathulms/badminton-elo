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
#
# 2026-07-17 live probe against extranet-lv.bwfbadminton.com/api:
#   * day_matches ............ 200, full match shape across all disciplines.
#     THIS IS THE WORKING COLLECTOR — see the `scrape_days` command.
#   * vue_tournament_detail .. 404 (every param/path variant tried)
#   * vue_tournament_draws ... 404 as `vue-tournament-draws`; a sibling
#     `tournaments/draws` returns 500 (exists, but the required params are not
#     guessable and the error body is a generic "Server Error")
#   * vue_tournament_draw_data 404
#   * players / match_statistics 404
#
# 2026-07-17 UPDATE from a real browser network-tab capture (bwfworldtour.
# bwfbadminton.com): the vue-* endpoints DO NOT sit under /api/tournaments/ —
# they are at /api/ directly (and match-center is under /api/match-center/),
# and the requests carry an Origin/Referer of bwfworldtour.bwfbadminton.com.
# Confirmed working:
#   * vue-grouped-year-tournaments ... the season CALENDAR (enumeration source);
#     ?year=YYYY&category[]=..(repeated)..&state=all. Each entry has the real
#     numeric id, GUID code, dates, and category/tier — 200.
#   * match-center/vue-current-live .. currently-live tournaments — 200.
#   * vue-tournament-detail .......... ?tmtId={numeric id} — full metadata.
#   * vue-tournament-draws ........... ?tmtTab=draw&tmtId={id} — draw list WITH
#     the qualification flag, stage_name and size.
#   * vue-tournament-draw-data ....... ?tmtTab=draw&tmtId={id}&drawId={value} —
#     PRIMARY results source; top-level `matches` array + `results` bracket map.
# The key was `tmtId` (NUMERIC id, from the calendar), not the GUID code.
#
# Category ids for the calendar/live filters map to World Tour tiers:
#   22..26 span Super 300 → Super 1000 + Finals (pass all five for everything).
CALENDAR_CATEGORIES = (22, 23, 24, 25, 26)

# Sent on every request (see BwfClient). The vue-* endpoints require them.
REQUEST_ORIGIN = "https://bwfworldtour.bwfbadminton.com"
REQUEST_REFERER = "https://bwfworldtour.bwfbadminton.com/"

CONFIRMED = {
    "day_matches": True,
    "vue_grouped_year_tournaments": True,
    "vue_current_live": True,
    "vue_tournament_detail": True,
    "vue_tournament_draws": True,
    "vue_tournament_draw_data": True,
    "players": False,
    "match_statistics": False,
}


def _category_qs(categories) -> str:
    """Repeated `category[]=` params, literal (matches the browser exactly)."""
    cats = CALENDAR_CATEGORIES if categories is None else categories
    return "&".join(f"category[]={c}" for c in cats)


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


def vue_grouped_year_tournaments(year: int, categories=None, state: str = "all") -> str:
    """Season CALENDAR — every tournament in a year, grouped by month.

    CONFIRMED (2026-07-17). Each tournament carries the real numeric id, GUID
    code, start/end dates, category (tier), country and prize money — this is
    the enumeration + tier source. Note: NOT under /api/tournaments/.
    """
    return f"{BASE}/vue-grouped-year-tournaments?year={year}&{_category_qs(categories)}&state={state}"


def vue_current_live(categories=None) -> str:
    """Currently-live tournaments (match-center). CONFIRMED (2026-07-17)."""
    return f"{BASE}/match-center/vue-current-live?{_category_qs(categories)}"


# --- TO CONFIRM (response shapes known; request params are best guesses) ------

def vue_tournament_detail(tmt_id: int | str) -> str:
    """Tournament metadata (id, name, dates, categoryModel.name = tier,
    tournament_series_id, prize_money, venue_*). CONFIRMED 2026-07-17.

    Keyed by the NUMERIC id via `tmtId` (not the GUID code) — get the id from
    the calendar (vue_grouped_year_tournaments) or a stored Tournament.
    """
    return _url(VUE_BASE, "vue-tournament-detail", tmtId=tmt_id)


def vue_tournament_draws(tmt_id: int | str) -> str:
    """List of draws in a tournament: results[] with value, text (e.g. "XD" or
    "XD - Qualification"), doubles, qualification (0/1), stage_name, size.
    Filter qualification==0 for the main draw. CONFIRMED 2026-07-17.
    """
    return _url(VUE_BASE, "vue-tournament-draws", tmtTab="draw", tmtId=tmt_id)


def vue_tournament_draw_data(tmt_id: int | str, draw_value: str | int) -> str:
    """PRIMARY results source: full bracket for one draw. Top level carries a
    flat `matches` array (every round, game-by-game scores, player ids, status)
    plus a `results` bracket map. CONFIRMED 2026-07-17.

    `draw_value` is the `value` from vue_tournament_draws (e.g. "10" = XD main),
    passed as `drawId`.
    """
    return _url(VUE_BASE, "vue-tournament-draw-data",
                tmtTab="draw", tmtId=tmt_id, drawId=draw_value)


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
