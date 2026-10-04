"""Rally-level ("points") engine: scoring maths, symmetry, engine selection."""
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pytest

from rating import GameRecord, MatchRecord, RatingConfig, run
from rating.points import game_win_prob, make_predictor, match_win_prob
from rating.predict import predictor_for, win_probability
from rating.run import period_update

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _brute_game(p, target, cap):
    @lru_cache(None)
    def f(a, b):
        if a == cap or (a >= target and a - b >= 2):
            return 1.0
        if b == cap or (b >= target and b - a >= 2):
            return 0.0
        return p * f(a + 1, b) + (1 - p) * f(a, b + 1)
    return f(0, 0)


@pytest.mark.parametrize("target,cap", [(21, 30), (15, 21), (11, 15)])
def test_game_probability_matches_the_scoring_rules(target, cap):
    for p in (0.2, 0.45, 0.5, 0.53, 0.7):
        assert math.isclose(game_win_prob(p, target, cap), _brute_game(p, target, cap), abs_tol=1e-12)


def test_match_probability_amplifies_the_rally_edge():
    assert match_win_prob(0.5) == pytest.approx(0.5)
    assert match_win_prob(0.55) > 0.8  # a small rally edge wins most matches


def test_points_predictor_is_symmetric():
    pred = make_predictor(0.13)
    p, q = pred(1800, 70, 1650, 110), pred(1650, 110, 1800, 70)
    assert p > 0.5 and p + q == pytest.approx(1.0, abs=1e-6)


def test_engine_and_predictor_follow_config():
    glicko, points = RatingConfig(), RatingConfig(engine="points")
    assert predictor_for(glicko) is win_probability
    assert predictor_for(points)(1700, 80, 1500, 80) == pytest.approx(
        make_predictor(points.rally_beta)(1700, 80, 1500, 80))
    with pytest.raises(ValueError):
        period_update(RatingConfig(engine="elo"))


def test_points_engine_rewards_the_rally_margin():
    def m(mid, a, b, games):
        return MatchRecord(match_id=mid, event="MS", match_time_utc=T0, round_order=1,
                           winner_side=1, score_status="Normal", scoring_format="3x21",
                           rating_excluded=False, side1_player_ids=(a,), side2_player_ids=(b,),
                           games=tuple(GameRecord(i + 1, x, y) for i, (x, y) in enumerate(games)),
                           tournament_id=mid)
    cfg = RatingConfig(engine="points")
    close = run([m(1, 1, 2, ((22, 20), (21, 19)))], cfg).ratings[(1, "MS")].mu
    blowout = run([m(2, 3, 4, ((21, 5), (21, 7)))], cfg).ratings[(3, "MS")].mu
    assert blowout > close > 1500
