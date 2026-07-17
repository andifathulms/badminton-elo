"""API tests (PRD §12) — real MM2026 XD draw ingested + rated, then served.

Uses DRF's test client against a separate test database, so it is safe to run
while a scrape writes to the dev db.sqlite3.
"""
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.ingest.models import Draw, Match, Tournament
from apps.ingest.normalize import normalize_draw_data
from apps.ingest.schemas import DrawData

FIXTURE = Path(__file__).parent / "fixtures" / "draw_data_mm2026_xd.json"


@pytest.fixture
def api(db):
    t = Tournament.objects.create(
        tournament_id=5229, code="MM-2026", name="Malaysia Masters 2026",
        category_name="HSBC BWF World Tour Super 500",
    )
    draw = Draw.objects.create(
        tournament=t, draw_value="10", event="XD", stage="Main Draw", doubles=True
    )
    data = DrawData.model_validate(json.loads(FIXTURE.read_text()))
    normalize_draw_data(data, tournament=t, draw=draw)
    call_command("rate", verbosity=0)
    return APIClient()


def test_leaderboard_requires_valid_event(api):
    assert api.get("/api/leaderboard").status_code == 400
    assert api.get("/api/leaderboard?event=ZZ").status_code == 400


def test_leaderboard_ranks_by_conservative_rating(api):
    r = api.get("/api/leaderboard?event=XD&min_matches=1")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0
    results = body["results"]
    # Descending by the conservative rating (mu - 2*rd).
    ratings = [row["rating"] for row in results]
    assert ratings == sorted(ratings, reverse=True)
    # Shape: nested player brief + rating fields.
    top = results[0]
    assert {"player", "event", "rating", "mu", "rd"} <= set(top)
    assert top["event"] == "XD"
    assert {"player_id", "name_display"} <= set(top["player"])


def test_leaderboard_pagination(api):
    r = api.get("/api/leaderboard?event=XD&min_matches=1&limit=3")
    body = r.json()
    assert len(body["results"]) <= 3
    assert "next" in body


def test_player_detail_lists_ratings(api):
    pid = Match.objects.get(match_id=1518158).lineup.first().player_id
    r = api.get(f"/api/players/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["player_id"] == pid
    assert any(rr["event"] == "XD" for rr in body["ratings"])


def test_player_history(api):
    pid = Match.objects.get(match_id=1518158).lineup.first().player_id
    r = api.get(f"/api/players/{pid}/history?event=XD")
    assert r.status_code == 200
    points = r.json()
    assert points and all(p["event"] == "XD" for p in points)
    assert {"mu_before", "mu_after", "delta", "applied_utc"} <= set(points[0])


def test_match_detail_has_lineup_and_games(api):
    r = api.get("/api/matches/1518158")
    assert r.status_code == 200
    body = r.json()
    assert body["event"] == "XD"
    assert body["winner_side"] == 2
    assert len(body["lineup"]) == 4  # doubles: two per side
    assert [(g["side1_points"], g["side2_points"]) for g in body["games"]] == [
        (13, 21), (21, 15), (11, 21)
    ]
    assert body["tournament"]["tournament_id"] == 5229
    # Per-player ELO deltas from this match; winners gain, losers lose.
    elo = body["elo"]
    assert len(elo) == 4
    assert any(v > 0 for v in elo.values()) and any(v < 0 for v in elo.values())


def test_player_matches_with_elo_delta(api):
    pid = Match.objects.get(match_id=1518158).lineup.filter(side=2).first().player_id
    r = api.get(f"/api/players/{pid}/matches")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    m = next(x for x in body["results"] if x["match_id"] == 1518158)
    assert m["won"] is True  # side 2 advanced
    assert m["elo_delta"] is not None
    assert m["opponents"] and m["score"]
    assert m["tournament"]["tournament_id"] == 5229


def test_peak_ranking(api):
    # Peak board ranks by all-time peak mu and exposes peak fields.
    r = api.get("/api/leaderboard?event=XD&min_matches=1&ranking=peak")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    peaks = [row["peak_mu"] for row in results]
    assert all(p is not None for p in peaks)
    assert peaks == sorted(peaks, reverse=True)
    # Peak mu is always >= current mu (best-ever can't be below now).
    for row in results:
        assert row["peak_mu"] >= row["mu"] - 1e-6


def test_events_endpoint(api):
    r = api.get("/api/events")
    assert r.status_code == 200
    rows = {row["event"]: row["rated_players"] for row in r.json()}
    assert rows["XD"] > 0
    assert rows["MS"] == 0  # only XD was ingested
