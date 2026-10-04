"""Incremental `rate` must store exactly what `rate --rebuild` stores."""
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db.models import Max

from apps.ingest.models import (
    Draw, Game, Match, MatchPlayer, PlayerRating, RatingHistory, Tournament,
)
from apps.ingest.normalize import normalize_draw_data
from apps.ingest.schemas import DrawData

FIXTURE = Path(__file__).parent / "fixtures" / "draw_data_mm2026_xd.json"
RATING_FIELDS = ("player_id", "event", "mu", "rd", "sigma", "matches_played",
                 "last_match_utc", "peak_mu", "peak_rd", "peak_utc", "wins",
                 "losses", "form", "rank", "rank_gender")
HISTORY_FIELDS = ("player_id", "event", "match_id", "mu_before", "mu_after",
                  "rd_before", "rd_after", "delta", "applied_utc")


def _rate(*args):
    out = StringIO()
    call_command("rate", *args, stdout=out)
    return out.getvalue()


def _snapshot():
    return (
        sorted(PlayerRating.objects.values_list(*RATING_FIELDS), key=repr),
        sorted(RatingHistory.objects.values_list(*HISTORY_FIELDS), key=repr),
    )


@pytest.fixture
def base(db):
    t = Tournament.objects.create(tournament_id=5229, code="MM-2026", name="MM 2026",
                                  category_name="HSBC BWF World Tour Super 500")
    draw = Draw.objects.create(tournament=t, draw_value="10", event="XD",
                               stage="Main Draw", doubles=True)
    normalize_draw_data(DrawData.model_validate(json.loads(FIXTURE.read_text())),
                        tournament=t, draw=draw)
    players = list(MatchPlayer.objects.values_list("player_id", flat=True).distinct()[:8])
    latest = Match.objects.aggregate(m=Max("match_time_utc"))["m"]
    return players, latest


def _add_match(mid, tid, players, when, winner=1, pts=(21, 15)):
    t, _ = Tournament.objects.get_or_create(tournament_id=tid, defaults={"name": f"T{tid}"})
    m = Match.objects.create(match_id=mid, tournament=t, event="XD", round_name="R16",
                             round_order=1, match_time_utc=when, score_status="Normal",
                             winner_side=winner, scoring_format="3x21")
    for side, pair in ((1, players[:2]), (2, players[2:4])):
        for p in pair:
            MatchPlayer.objects.create(match=m, side=side, player_id=p)
    Game.objects.create(match=m, game_no=1, side1_points=pts[0], side2_points=pts[1])
    Game.objects.create(match=m, game_no=2, side1_points=pts[0], side2_points=pts[1])


def test_incremental_equals_rebuild(base):
    players, latest = base
    _add_match(900001, 7001, players, latest + timedelta(days=7))
    assert "Plan: full" in _rate()
    assert "nothing changed" in _rate()

    # The ongoing tournament gains a match, and a new tournament appears.
    _add_match(900002, 7001, players[2:] + players[:2], latest + timedelta(days=8), winner=2)
    _add_match(900003, 7002, players[4:] + players[:4], latest + timedelta(days=20))
    out = _rate()
    assert "Plan: incremental" in out, out
    incremental_state = _snapshot()

    _rate("--rebuild")
    assert _snapshot() == incremental_state


def test_backfill_inside_undo_window_replays_exactly(base):
    players, latest = base
    _add_match(900001, 7001, players, latest + timedelta(days=7))
    _rate()
    _add_match(900010, 7000, players, latest - timedelta(days=60))  # before MM 2026
    assert "Plan: incremental (replaying 3 tournament(s))" in _rate()
    state = _snapshot()
    _rate("--rebuild")
    assert _snapshot() == state


def test_change_older_than_undo_window_forces_full(base):
    players, latest = base
    # MM 2026 ends up > UNDO_DAYS (120) before the newest tournament: no log.
    _add_match(900001, 7001, players, latest + timedelta(days=200))
    _rate()
    _add_match(900010, 7000, players, latest - timedelta(days=60))
    assert "Plan: full (a changed tournament is older than the undo window)" in _rate()


def test_settings_change_forces_full(base, settings):
    _rate()
    settings.RATING = {**settings.RATING, "LAMBDA": 1.5}
    assert "Plan: full (rating settings changed)" in _rate()
