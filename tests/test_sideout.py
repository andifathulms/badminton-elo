"""Side-out (pre-2006) game-score likelihood — rating/sideout.py."""
import pytest

from rating.sideout import game_terms, outcome_probs, target_of


@pytest.mark.parametrize("target", [7, 11, 15])
@pytest.mark.parametrize("doubles", [False, True])
def test_outcomes_are_a_distribution(target, doubles):
    for p in (0.3, 0.5, 0.62):
        assert sum(outcome_probs(p, target, doubles, True).values()) == pytest.approx(1.0)


def test_even_rallies_favour_the_first_server_in_singles_only():
    def win(o):
        return sum(v for k, v in o.items() if k[0] in ("W", "Wd"))
    assert win(outcome_probs(0.5, 15, False, True)) > 0.5
    # first hand down makes doubles fair
    assert win(outcome_probs(0.5, 15, True, True)) == pytest.approx(0.5)


def test_side_out_amplifies_a_rally_edge():
    o = outcome_probs(0.55, 15, False, True)
    assert sum(v for k, v in o.items() if k[0] in ("W", "Wd")) > 0.75


def test_targets_from_winner_score():
    assert [target_of(w) for w in (7, 8, 11, 12, 13, 15, 17, 18, 21, 9)] == \
        [7, 7, 11, 11, 11, 15, 15, 15, None, None]


def test_blowout_says_more_than_a_close_win():
    big, _ = game_terms(0.5, [(15, 2), (15, 3)], False)
    close, _ = game_terms(0.5, [(17, 15), (15, 13)], False)
    lost, _ = game_terms(0.5, [(2, 15), (3, 15)], False)
    assert big > close > 0 > lost


def test_unreadable_games_fall_back():
    assert game_terms(0.5, [(21, 10), (21, 12)], False) is None  # rally scores
    assert game_terms(0.5, [(9, 4)], False) is None  # unfinished
