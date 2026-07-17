"""M1 acceptance (PRD §13) against the REAL captured Malaysia Masters 2026 XD draw.

Asserts the milestone exactly: 31 main-draw matches; winners correct including
the retired 1518150 (winner side 2 despite trailing); players deduped by id;
Game rows match scorelines; a second normalize produces zero changes.
"""
import json
from pathlib import Path

import pytest

from apps.ingest.models import Draw, Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.normalize import normalize_draw_data
from apps.ingest.schemas import DrawData

FIXTURE = Path(__file__).parent / "fixtures" / "draw_data_mm2026_xd.json"


def _draw_data() -> DrawData:
    return DrawData.model_validate(json.loads(FIXTURE.read_text()))


@pytest.fixture
def ingested(db):
    t = Tournament.objects.create(
        tournament_id=5229, code="MM-2026", name="PERODUA Malaysia Masters 2026"
    )
    draw = Draw.objects.create(
        tournament=t, draw_value="10", event="XD", stage="Main Draw", doubles=True
    )
    counts = normalize_draw_data(_draw_data(), tournament=t, draw=draw)
    return t, draw, counts


def test_m1_thirtyone_main_draw_matches(ingested):
    _, _, (n, skipped) = ingested
    assert n == 31 and skipped == 0
    assert Match.objects.count() == 31


def test_m1_retired_match_winner_is_side_2_despite_trailing(ingested):
    """The real retirement: winner from the `winner` field, not the scoreline."""
    m = Match.objects.get(match_id=1518150)
    assert m.winner_side == 2
    assert m.score_status == "Retired"
    assert m.rating_excluded is False  # retirements count (reduced weight)
    # The side that led on points is NOT the winner — proving no score inference.
    g1 = m.games.order_by("game_no").first()
    assert g1.side1_points > g1.side2_points  # side 1 led
    assert m.winner_side == 2  # yet side 2 advanced


def test_m1_all_matches_are_xd(ingested):
    assert set(Match.objects.values_list("event", flat=True)) == {"XD"}


def test_m1_players_deduped_by_id(ingested):
    """No duplicate Player rows; a player appearing in R32 and later is one row."""
    # every MatchPlayer.player_id resolves to exactly one Player
    ids = set(MatchPlayer.objects.values_list("player_id", flat=True))
    assert Player.objects.filter(player_id__in=ids).count() == len(ids)
    # someone who advanced played more than one match, still a single Player row
    from django.db.models import Count

    multi = (
        MatchPlayer.objects.values("player_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    assert multi.exists()


def test_m1_games_match_scorelines(ingested):
    """Game rows reproduce each match's score[] with home=side1, away=side2."""
    raw_by_id = {m.id: m for m in _draw_data().matches}
    for match in Match.objects.all():
        raw = raw_by_id[match.match_id]
        got = list(
            match.games.order_by("game_no").values_list("side1_points", "side2_points")
        )
        expected = [(g.home, g.away) for g in raw.score]
        assert got == expected, f"match {match.match_id} games mismatch"


def test_m1_second_normalize_changes_nothing(ingested):
    t, draw, _ = ingested
    before = (
        Match.objects.count(),
        Player.objects.count(),
        Game.objects.count(),
        MatchPlayer.objects.count(),
    )
    n, skipped = normalize_draw_data(_draw_data(), tournament=t, draw=draw)
    after = (
        Match.objects.count(),
        Player.objects.count(),
        Game.objects.count(),
        MatchPlayer.objects.count(),
    )
    assert before == after
    assert (n, skipped) == (31, 0)
