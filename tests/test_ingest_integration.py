"""Integration: ingest a draw-data fixture and assert the M1 contract (PRD §13).

Runs the real normalizer against a synthetic XD draw that reproduces the
critical edge cases. When the captured Malaysia Masters 2026 XD payload is
dropped in, point FIXTURE at it and tighten the count assertions to 31.
"""
import json
from pathlib import Path

import pytest

from apps.ingest.models import Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.normalize import normalize_draw_data
from apps.ingest.schemas import DrawData

FIXTURE = Path(__file__).parent / "fixtures" / "draw_data_xd_sample.json"


def _load_draw_data() -> DrawData:
    payload = json.loads(FIXTURE.read_text())
    return DrawData.model_validate(payload["results"])


@pytest.fixture
def tournament(db):
    return Tournament.objects.create(
        tournament_id=5229, code="MM-2026", name="Malaysia Masters 2026"
    )


def _ingest(tournament):
    data = _load_draw_data()
    return normalize_draw_data(data, tournament=tournament, draw=None)


def test_all_matches_ingested(tournament):
    ingested, skipped = _ingest(tournament)
    assert (ingested, skipped) == (4, 0)
    assert Match.objects.count() == 4


def test_retired_match_344_winner_is_side_2_despite_trailing(tournament):
    """CRITICAL: winner comes from the `winner` field, not the scoreline."""
    _ingest(tournament)
    m = Match.objects.get(match_id=344)
    assert m.winner_side == 2  # advanced
    assert m.score_status == "Retired"
    assert m.rating_excluded is False  # retirements still count (reduced weight)
    # side 1 actually led on points — proving we did NOT infer winner from score.
    g = Game.objects.get(match=m, game_no=1)
    assert (g.side1_points, g.side2_points) == (11, 5)


def test_walkover_is_rating_excluded(tournament):
    _ingest(tournament)
    m = Match.objects.get(match_id=347)
    assert m.score_status == "Walkover"
    assert m.rating_excluded is True
    assert m.games.count() == 0  # empty score[] -> no games


def test_players_deduped_by_id_across_matches(tournament):
    """GAO Jia Xuan (57943) appears in matches 341 and 361 — one Player row."""
    _ingest(tournament)
    assert Player.objects.filter(player_id=57943).count() == 1
    # She is on side 1 of both matches she played.
    lineups = MatchPlayer.objects.filter(player_id=57943)
    assert lineups.count() == 2
    assert set(lineups.values_list("side", flat=True)) == {1}


def test_side_orientation_and_games(tournament):
    _ingest(tournament)
    m = Match.objects.get(match_id=361)
    games = list(m.games.order_by("game_no").values_list("side1_points", "side2_points"))
    assert games == [(21, 18), (19, 21), (21, 19)]  # home=side1, away=side2, in order


def test_scoring_format_defaults_from_date(tournament):
    _ingest(tournament)
    # 2026 match -> 3x21 by date default (PRD §6.5).
    assert Match.objects.get(match_id=341).scoring_format == "3x21"


def test_reingest_is_idempotent(tournament):
    """A second ingest changes nothing (PRD §6.1) — M1 're-run changes nothing'."""
    _ingest(tournament)
    before = {
        "matches": Match.objects.count(),
        "players": Player.objects.count(),
        "games": Game.objects.count(),
        "lineup": MatchPlayer.objects.count(),
    }
    ingested, skipped = _ingest(tournament)
    after = {
        "matches": Match.objects.count(),
        "players": Player.objects.count(),
        "games": Game.objects.count(),
        "lineup": MatchPlayer.objects.count(),
    }
    assert before == after
    assert (ingested, skipped) == (4, 0)
