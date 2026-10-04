from rating.peaks import peak_ratings
from rating.types import RatingDelta


def _d(pid, mu, rd, t):
    return RatingDelta(player_id=pid, event="MS", match_id=t, mu_before=mu,
                       mu_after=mu, rd_before=rd, rd_after=rd, delta=0.0,
                       applied_utc=t)


def test_unsettled_spike_does_not_count_as_peak():
    hist = [_d(1, 2100, 220, 1), _d(1, 1900, 90, 2), _d(1, 1950, 80, 3)]
    assert peak_ratings(hist, 100.0)[(1, "MS")] == (1950, 80, 3)


def test_never_settled_falls_back_to_raw_max():
    hist = [_d(2, 1700, 250, 1), _d(2, 1800, 200, 2)]
    assert peak_ratings(hist, 100.0)[(2, "MS")] == (1800, 200, 2)


def test_start_peaks_carry_over():
    start = {(1, "MS"): (2000, 70, 0)}
    assert peak_ratings([_d(1, 1950, 80, 3)], 100.0, start)[(1, "MS")] == (2000, 70, 0)
    assert peak_ratings([_d(1, 2050, 80, 3)], 100.0, start)[(1, "MS")] == (2050, 80, 3)
