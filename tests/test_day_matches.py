"""Day-matches ingestion tests against a REAL captured payload (PRD §4.4).

Uses the committed Malaysia Masters 2026 finals-day fixture, so this verifies
the actual BWF response shape parses and normalizes correctly.
"""
import json
from pathlib import Path

import pytest

from apps.ingest.models import Draw, Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.normalize import (
    normalize_day_matches,
    synthetic_tournament_id,
    upsert_tournament_from_code,
)
from apps.ingest.schemas import DayMatches

FIXTURE = Path(__file__).parent / "fixtures" / "day_matches_mm2026_2026-05-24.json"
CODE = "71AC3AB2-C072-444C-B479-4AC73C756C14"


def _matches():
    return DayMatches.validate_python(json.loads(FIXTURE.read_text()))


@pytest.fixture
def ingested(db):
    matches = _matches()
    name = matches[0].tournament_name
    t = upsert_tournament_from_code(CODE, name)
    counts = normalize_day_matches(matches, tournament=t)
    return t, counts


def test_finals_day_fully_ingested(ingested):
    _, (ingested_n, skipped) = ingested
    assert (ingested_n, skipped) == (5, 0)
    assert Match.objects.count() == 5


def test_synthetic_tournament_id_is_stable(ingested):
    t, _ = ingested
    assert t.tournament_id == synthetic_tournament_id(CODE)
    assert t.code == CODE
    assert t.name == "PERODUA Malaysia Masters 2026"


def test_all_five_disciplines_present(ingested):
    events = set(Match.objects.values_list("event", flat=True))
    assert events == {"MS", "WS", "MD", "WD", "XD"}


def test_xd_final_scores_and_winner(ingested):
    # match 1518158: XD Final, winner side 2, 13-21 21-15 11-21 (home=side1).
    m = Match.objects.get(match_id=1518158)
    assert m.event == "XD" and m.round_name == "Final"
    assert m.winner_side == 2
    games = list(m.games.order_by("game_no").values_list("side1_points", "side2_points"))
    assert games == [(13, 21), (21, 15), (11, 21)]


def test_match_time_is_utc_aware(ingested):
    m = Match.objects.get(match_id=1518158)
    assert m.match_time_utc is not None
    assert m.match_time_utc.utcoffset().total_seconds() == 0


def test_doubles_lineups_have_two_players(ingested):
    md = Match.objects.get(match_id=1518090)  # MD final
    assert MatchPlayer.objects.filter(match=md, side=1).count() == 2
    assert MatchPlayer.objects.filter(match=md, side=2).count() == 2


def test_draws_grouped_by_drawcode(ingested):
    # Five finals -> five distinct draws (one per discipline).
    assert Draw.objects.count() == 5
    assert set(Draw.objects.values_list("event", flat=True)) == {
        "MS",
        "WS",
        "MD",
        "WD",
        "XD",
    }


def test_reingest_is_idempotent(ingested):
    t, _ = ingested
    before = (Match.objects.count(), Player.objects.count(), Game.objects.count())
    normalize_day_matches(_matches(), tournament=t)
    after = (Match.objects.count(), Player.objects.count(), Game.objects.count())
    assert before == after
