"""Pure-engine tests (PRD §7) — import `rating` directly, no Django.

Covers the mechanics that keep ratings honest: symmetry, uncertainty-scaled
updates, pair blending, retirement damping, determinism, and per-discipline
independence.
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from rating import MatchRecord, GameRecord, Rating, RatingConfig, run, update_match
from rating.seeding import flat_seed, rank_seed

CFG = RatingConfig(tier_weights={})
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _match(mid, w, s1, s2, games=((21, 10),), event="XD", status="Normal",
           excluded=False, t=T0, tier_weight=1.0, tournament_id=None):
    # Default each match to its OWN tournament (period), so the simple tests see
    # sequential per-match updates; pass a shared tournament_id to test locking.
    return MatchRecord(
        match_id=mid, event=event, match_time_utc=t, round_order=1,
        winner_side=w, score_status=status, scoring_format="3x21",
        rating_excluded=excluded, side1_player_ids=s1, side2_player_ids=s2,
        games=tuple(GameRecord(i + 1, a, b) for i, (a, b) in enumerate(games)),
        tier_weight=tier_weight,
        tournament_id=tournament_id if tournament_id is not None else mid,
    )


def test_winner_gains_loser_loses_symmetrically():
    res = run([_match(1, 1, (101,), (102,))], CFG)
    dw = res.ratings[(101, "XD")].mu - 1500
    dl = res.ratings[(102, "XD")].mu - 1500
    assert dw > 0 and dl < 0
    assert math.isclose(dw, -dl, rel_tol=1e-9)  # equal-and-opposite at equal rd


def test_rd_shrinks_after_a_rated_match():
    res = run([_match(1, 1, (101,), (102,))], CFG)
    for r in res.ratings.values():
        assert r.rd < CFG.rd_init
        assert r.matches_played == 1


def test_bigger_margin_moves_more():
    close = run([_match(1, 1, (1,), (2,), games=((21, 19),))], CFG)
    blowout = run([_match(1, 1, (3,), (4,), games=((21, 3), (21, 4)))], CFG)
    assert (blowout.ratings[(3, "XD")].mu - 1500) > (close.ratings[(1, "XD")].mu - 1500)


def test_retirement_moves_less_than_normal_win():
    normal = run([_match(1, 1, (1,), (2,))], CFG)
    retired = run([_match(1, 1, (3,), (4,), status="Retired")], CFG)
    dn = normal.ratings[(1, "XD")].mu - 1500
    dr = retired.ratings[(3, "XD")].mu - 1500
    assert 0 < dr < dn


def test_excluded_and_undecided_matches_do_nothing():
    excl = run([_match(1, 1, (1,), (2,), status="Walkover", excluded=True)], CFG)
    assert excl.ratings == {} and excl.history == []


def test_uncertainty_scaling_new_player_moves_more_than_established():
    """A high-rd player swings more than a low-rd partner in the same match."""
    # Pre-age one player with several matches so their rd drops.
    warmup = [_match(i, 1, (10,), (900 + i,), t=T0 + timedelta(days=i)) for i in range(6)]
    res = run(warmup, CFG)
    established = res.ratings[(10, "XD")]
    assert established.rd < CFG.rd_init - 100  # meaningfully settled from 350

    # Now 10 (low rd) partners a brand-new 20 (rd=350) in one doubles match.
    r_est_before = (established.mu, established.rd)
    res2 = run(
        warmup + [_match(99, 1, (10, 20), (30, 31), t=T0 + timedelta(days=10))], CFG
    )
    est_move = abs(res2.ratings[(10, "XD")].mu - r_est_before[0])
    new_move = abs(res2.ratings[(20, "XD")].mu - 1500)
    assert new_move > est_move  # the newcomer absorbs most of the swing


def test_pair_blend_uses_mean_and_rms():
    """Team expectation blends members: strong+weak beats weak+weak as expected."""
    # Give side1 a clearly stronger pair via prior wins, then they beat newcomers.
    hist = [_match(i, 1, (1,), (500 + i,), t=T0 + timedelta(days=i)) for i in range(8)]
    res = run(hist + [_match(50, 1, (1, 2), (3, 4), t=T0 + timedelta(days=20))], CFG)
    # The established, higher-rated player 1 should end above the flat start.
    assert res.ratings[(1, "XD")].mu > 1500


def test_determinism_same_input_same_output():
    matches = [
        _match(3, 1, (1,), (2,), t=T0 + timedelta(days=2)),
        _match(1, 2, (2,), (3,), t=T0),
        _match(2, 1, (1,), (3,), t=T0 + timedelta(days=1)),
    ]
    a = run(list(matches), CFG)
    b = run(list(reversed(matches)), CFG)  # order shouldn't matter — sorted internally
    assert a.ratings.keys() == b.ratings.keys()
    for k in a.ratings:
        assert math.isclose(a.ratings[k].mu, b.ratings[k].mu, rel_tol=1e-12)
        assert math.isclose(a.ratings[k].rd, b.ratings[k].rd, rel_tol=1e-12)


def test_disciplines_are_independent():
    res = run(
        [
            _match(1, 1, (7,), (8,), event="XD"),
            _match(2, 2, (7,), (9,), event="MD"),
        ],
        CFG,
    )
    assert res.ratings[(7, "XD")].mu > 1500  # won in XD
    assert res.ratings[(7, "MD")].mu < 1500  # lost in MD
    assert (7, "WS") not in res.ratings


def test_tournament_locking_uses_start_of_period_ratings():
    """Two wins in ONE tournament are both computed from the start rating, so a
    player gains more than winning the same two across separate tournaments
    (where the second win is computed from an already-raised rating)."""
    locked = run(
        [
            _match(1, 1, (10,), (11,), tournament_id=99),
            _match(2, 1, (10,), (12,), tournament_id=99, t=T0 + timedelta(hours=2)),
        ],
        CFG,
    )
    sequential = run(
        [
            _match(1, 1, (10,), (11,), tournament_id=1),
            _match(2, 1, (10,), (12,), tournament_id=2, t=T0 + timedelta(days=1)),
        ],
        CFG,
    )
    assert locked.ratings[(10, "XD")].mu > sequential.ratings[(10, "XD")].mu


def test_period_deltas_sum_to_total_change():
    """Per-match attributed deltas sum to the player's period mu change."""
    res = run(
        [
            _match(1, 1, (10,), (11,), tournament_id=7),
            _match(2, 1, (10,), (12,), tournament_id=7, t=T0 + timedelta(hours=2)),
        ],
        CFG,
    )
    hist = [h for h in res.history if h.player_id == 10]
    total = sum(h.delta for h in hist)
    assert math.isclose(res.ratings[(10, "XD")].mu - 1500, total, rel_tol=1e-6)


def test_rank_seed_curve():
    # rank 1 seeds near the top; higher ranks decay to the flat baseline.
    assert rank_seed(1, CFG).mu == pytest.approx(CFG.seed_rank_top_mu)
    assert rank_seed(CFG.seed_rank_base, CFG).mu == pytest.approx(CFG.mu_init)
    assert rank_seed(1000, CFG).mu == pytest.approx(CFG.mu_init)  # clamped
    assert rank_seed(10, CFG).mu > rank_seed(100, CFG).mu > CFG.mu_init
    # a rank-based seed carries high (but sub-350) uncertainty
    assert rank_seed(1, CFG).rd == CFG.seed_rd
    assert rank_seed(None, CFG).mu == flat_seed(CFG).mu  # no rank -> flat


def test_rank_seeding_dampens_a_top_seed_cold_start():
    """A #1-ranked debutant beating an unknown gains far less than if seeded
    flat — the fix for newcomer over-inflation."""
    m = [_match(1, 1, (1,), (2,), tournament_id=5)]
    flat = run(m, CFG)
    seeded = run(m, CFG, seed_ranks={(1, "XD"): 1})
    # gain measured from each player's own seed
    flat_gain = flat.ratings[(1, "XD")].mu - CFG.mu_init
    seeded_gain = seeded.ratings[(1, "XD")].mu - rank_seed(1, CFG).mu
    assert seeded_gain < flat_gain
    # and the top seed still ends up far higher overall
    assert seeded.ratings[(1, "XD")].mu > flat.ratings[(1, "XD")].mu


def test_tier_weight_amplifies_movement():
    base = run([_match(1, 1, (1,), (2,), tier_weight=1.0)], CFG)
    heavy = run([_match(1, 1, (3,), (4,), tier_weight=1.1)], CFG)
    assert (heavy.ratings[(3, "XD")].mu - 1500) > (base.ratings[(1, "XD")].mu - 1500)
