"""History engine (TrueSkill Through Time smoothing) + the all-time board."""
from datetime import datetime, timedelta, timezone

import pytest
from django.core.management import call_command

from rating import GameRecord, MatchRecord
from rating.history import best_point, display_scale, smooth

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _m(mid, w, s1, s2, days, event="MS"):
    return MatchRecord(match_id=mid, event=event, match_time_utc=T0 + timedelta(days=days),
                       round_order=1, winner_side=w, score_status="Normal",
                       scoring_format="3x21", rating_excluded=False,
                       side1_player_ids=s1, side2_player_ids=s2,
                       games=(GameRecord(1, 21, 10),), tournament_id=mid)


def test_dominant_player_is_rated_highest_everywhere_on_their_curve():
    ms = [_m(i, 1, (1,), (2 + i % 4,), i * 10) for i in range(40)]
    curves = smooth(ms)
    final = {pid: c[-1][1] for (pid, _), c in curves.items()}
    assert max(final, key=final.get) == 1
    day, mu, rd = best_point(curves[(1, "MS")])
    assert mu > 1500 and rd > 0


def test_doubles_use_their_own_display_scale():
    assert display_scale(2) > display_scale(1)
    ms = [_m(i, 1, (1, 2), (3, 4), i * 7, event="MD") for i in range(10)]
    assert set(smooth(ms)) == {(p, "MD") for p in (1, 2, 3, 4)}


def test_retired_and_excluded_matches_are_skipped():
    retired = MatchRecord(match_id=1, event="MS", match_time_utc=T0, round_order=1,
                          winner_side=1, score_status="Retired", scoring_format="3x21",
                          rating_excluded=False, side1_player_ids=(1,), side2_player_ids=(2,))
    assert smooth([retired]) == {}


@pytest.mark.django_db
def test_rate_history_feeds_the_alltime_board(client):
    import json
    from pathlib import Path

    from apps.ingest.models import Draw, PlayerRating, SmoothedRating, Tournament
    from apps.ingest.normalize import normalize_draw_data
    from apps.ingest.schemas import DrawData

    t = Tournament.objects.create(tournament_id=5229, name="MM 2026")
    draw = Draw.objects.create(tournament=t, draw_value="10", event="XD",
                               stage="Main Draw", doubles=True)
    fixture = Path(__file__).parent / "fixtures" / "draw_data_mm2026_xd.json"
    normalize_draw_data(DrawData.model_validate(json.loads(fixture.read_text())),
                        tournament=t, draw=draw)
    call_command("rate", verbosity=0)
    call_command("rate_history", verbosity=0)

    assert SmoothedRating.objects.filter(event="XD", year=2026).exists()
    # Everyone gets an all-time best except the pair whose only match was the
    # retirement (match 344) — retirements say little about skill.
    unrated = PlayerRating.objects.filter(alltime_mu=None)
    assert unrated.count() == 2
    assert all(r.matches_played == 1 for r in unrated)
    rows = client.get("/api/leaderboard?event=XD&ranking=peak&min_matches=1").json()["results"]
    best = [r["alltime_mu"] - 2 * r["alltime_rd"] for r in rows]
    assert best == sorted(best, reverse=True)


def test_fit_scale_maps_smoothed_onto_live():
    from rating.history import fit_scale, rescale

    a, b = fit_scale([(1500 + 2 * x, 1500 + x) for x in range(-300, 301, 50)])
    assert b == pytest.approx(0.5) and a == pytest.approx(750)
    assert rescale([(0, 2100.0, 100.0)], a, b) == [(0, pytest.approx(1800.0), pytest.approx(50.0))]
    assert fit_scale([(1, 2)]) == (0.0, 1.0)
