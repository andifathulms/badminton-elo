"""Backtest harness + read-side predictor (pure, no Django)."""
import math
from datetime import datetime, timedelta, timezone

from rating import GameRecord, MatchRecord, RatingConfig
from rating.backtest import backtest
from rating.predict import team_rating, win_probability

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _m(mid, w, s1, s2, days):
    return MatchRecord(
        match_id=mid, event="MS", match_time_utc=T0 + timedelta(days=days),
        round_order=1, winner_side=w, score_status="Normal", scoring_format="3x21",
        rating_excluded=False, side1_player_ids=s1, side2_player_ids=s2,
        games=(GameRecord(1, 21, 15), GameRecord(2, 21, 15)), tournament_id=mid,
    )


def test_win_probability_is_symmetric():
    p = win_probability(1700, 80, 1500, 120)
    q = win_probability(1500, 120, 1700, 80)
    assert math.isclose(p + q, 1.0, rel_tol=1e-12)
    assert p > 0.5


def test_team_rating_blends_mean_mu_rms_rd():
    mu, rd = team_rating([(1600, 30), (1400, 40)])
    assert mu == 1500
    assert math.isclose(rd, math.sqrt((900 + 1600) / 2))
    assert team_rating([]) is None


def test_backtest_rewards_a_consistent_favourite():
    # Player 1 beats everyone, every week: once rated, predictions should be
    # confidently right, so log-loss falls well below a coin flip (ln 2).
    ms = [_m(i, 1, (1,), (100 + i % 5,), i * 7) for i in range(1, 60)]
    res = backtest(ms, RatingConfig(), since=T0 + timedelta(days=200))
    assert res.n > 0
    assert res.accuracy == 1.0
    assert res.log_loss < math.log(2)


def test_backtest_respects_since_window():
    ms = [_m(i, 1, (1,), (2,), i) for i in range(1, 11)]
    assert backtest(ms, RatingConfig(), since=T0 + timedelta(days=100)).n == 0
    assert backtest(ms, RatingConfig()).n == 10


def test_predictor_shares_engine_scale_and_formula():
    # Read side and engine must agree on the Glicko-2 scale and g()/E shape:
    # with the opponent's phi set to the combined phi, they coincide.
    from rating import engine
    from rating.predict import SCALE

    assert SCALE == engine._SCALE
    mu1, rd1, mu2, rd2 = 1720.0, 70.0, 1580.0, 110.0
    phi_diff = math.sqrt(rd1**2 + rd2**2) / SCALE
    e = engine._expected((mu1 - 1500) / SCALE, (mu2 - 1500) / SCALE, phi_diff)
    assert math.isclose(win_probability(mu1, rd1, mu2, rd2), e, rel_tol=1e-12)
