"""Pure-engine tests for dominance / margin multiplier (PRD §7.3).

These import `rating` directly and never touch Django — proving the package is
usable standalone.
"""
from rating.dominance import dominance, margin_multiplier
from rating.types import GameRecord, RatingConfig

CFG = RatingConfig()


def test_dominance_is_winner_share_of_points():
    games = [GameRecord(1, 21, 15), GameRecord(2, 21, 10)]
    # winner side 1: 42 / (42 + 25)
    assert dominance(games, winner_side=1) == 42 / 67


def test_dominance_format_independent_ratio():
    # Same 2:1 point ratio in 3x21 and 3x15 formats yields identical dominance.
    d21 = dominance([GameRecord(1, 20, 10)], winner_side=1)
    d15 = dominance([GameRecord(1, 14, 7)], winner_side=1)
    assert round(d21, 6) == round(d15, 6)


def test_dominance_floored_for_close_wins():
    # A tight three-gamer must not dip below the 0.50 floor.
    games = [GameRecord(1, 21, 19), GameRecord(2, 19, 21), GameRecord(3, 21, 19)]
    assert dominance(games, winner_side=1, d_floor=0.50) >= 0.50


def test_dominance_no_points_returns_floor():
    assert dominance([], winner_side=1, d_floor=0.5) == 0.5


def test_margin_multiplier_clamped():
    # Total blowout clamps at M_MAX; even split sits near 1.0.
    assert margin_multiplier(1.0, CFG) == CFG.m_max
    assert abs(margin_multiplier(0.5, CFG) - 1.0) < 1e-9
    assert margin_multiplier(0.0, CFG) == CFG.m_min


def test_narrow_win_can_dampen_below_one():
    from rating import GameRecord, RatingConfig, dominance, margin_multiplier

    cfg = RatingConfig()
    # Won 2-1 but scored fewer points overall (21-19, 5-21, 21-19): d < 0.5.
    games = (GameRecord(1, 21, 19), GameRecord(2, 5, 21), GameRecord(3, 21, 19))
    d = dominance(games, 1, d_floor=cfg.d_floor)
    assert d < 0.5
    assert margin_multiplier(d, cfg) < 1.0
    # No points recorded -> neutral, never the minimum.
    assert margin_multiplier(dominance((), 1, d_floor=cfg.d_floor), cfg) == 1.0
