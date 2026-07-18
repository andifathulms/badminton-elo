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
    call_command("infer_gender", verbosity=0)
    call_command("build_pairs", "--min-matches", "1", verbosity=0)
    call_command("build_analytics", verbosity=0)
    call_command("build_cup_history", verbosity=0)
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
    # Per-player ELO for this match: before/after/delta; winners gain, losers lose.
    elo = body["elo"]
    assert len(elo) == 4
    deltas = [v["delta"] for v in elo.values()]
    assert any(d > 0 for d in deltas) and any(d < 0 for d in deltas)
    for v in elo.values():
        assert {"before", "after", "delta"} <= set(v)
    # Per-side (pair) combined ELO: one entry per side, mean of members.
    team = body["team_elo"]
    assert set(team) == {"1", "2"}
    assert {"before", "after", "delta"} <= set(team["1"])


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


def test_pairs_ranking(api):
    # XD draw -> XD partnerships ranked by combined strength.
    r = api.get("/api/pairs?event=XD&min_matches=1")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    ratings = [row["rating"] for row in results]
    assert ratings == sorted(ratings, reverse=True)
    top = results[0]
    assert {"player1", "player2", "matches_together", "win_pct"} <= set(top)
    assert top["event"] == "XD"
    assert top["player1"]["player_id"] != top["player2"]["player_id"]


def test_pairs_requires_doubles_event(api):
    assert api.get("/api/pairs?event=MS").status_code == 400


def test_pair_detail(api):
    top = api.get("/api/pairs?event=XD&min_matches=1").json()["results"][0]
    p1, p2 = top["player1"]["player_id"], top["player2"]["player_id"]
    r = api.get(f"/api/pairs/detail?event=XD&p1={p1}&p2={p2}")
    assert r.status_code == 200
    body = r.json()
    assert body["matches_together"] >= 1
    assert body["wins"] + body["losses"] == body["matches_together"]
    assert body["matches"] and body["matches"][0]["match_id"]
    assert body["pair"] is not None


def test_pairs_peak_ranking(api):
    r = api.get("/api/pairs?event=XD&min_matches=1&ranking=peak")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    peaks = [row["combined_peak_mu"] for row in results]
    assert all(p is not None for p in peaks)
    assert peaks == sorted(peaks, reverse=True)


def test_tournament_matches_clickable(api):
    r = api.get("/api/tournaments/5229/matches?event=XD")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 31
    m = body["results"][0]
    assert {"match_id", "side1", "side2", "score", "winner_side", "round_name"} <= set(m)
    assert m["side1"] and m["side2"]  # both sides populated for linking


def test_xd_gender_split(api):
    # XD players get a gender from the (implicit) singles/doubles context; here
    # the fixture is XD-only so gender is blank — the filter should return empty.
    men = api.get("/api/leaderboard?event=XD&min_matches=1&gender=M").json()
    women = api.get("/api/leaderboard?event=XD&min_matches=1&gender=F").json()
    allxd = api.get("/api/leaderboard?event=XD&min_matches=1").json()
    assert allxd["count"] >= men["count"] + women["count"]


def test_player_records(api):
    pid = Match.objects.get(match_id=1518158).lineup.filter(side=2).first().player_id
    body = api.get(f"/api/players/{pid}").json()
    rec = {r["event"]: r for r in body["records"]}
    assert "XD" in rec
    assert rec["XD"]["matches"] == rec["XD"]["wins"] + rec["XD"]["losses"]
    assert rec["XD"]["wins"] >= 1  # they advanced at least once


def test_player_search(api):
    # search by a substring of a real name in the fixture
    r = api.get("/api/players?q=GAO")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results and all("GAO" in p["name_display"].upper() for p in results)


def test_tournaments_list_and_detail(api):
    lst = api.get("/api/tournaments").json()
    assert lst["count"] >= 1
    row = lst["results"][0]
    assert row["tournament_id"] == 5229
    assert row["match_count"] == 31

    detail = api.get("/api/tournaments/5229").json()
    assert "Malaysia Masters" in detail["name"]
    assert any(d["event"] == "XD" for d in detail["draws"])
    assert any(e["event"] == "XD" for e in detail["events"])
    # the XD final crowns champions (side that advanced)
    xd_final = next(f for f in detail["finals"] if f["event"] == "XD")
    assert len(xd_final["champions"]) == 2


def test_match_statistics_served_from_cache(api):
    from apps.ingest.models import MatchStatistics

    MatchStatistics.objects.create(
        match_id=1518158,
        team1_rallies_won=40,
        team1_rallies_played=90,
        team2_rallies_won=50,
        team2_rallies_played=90,
        duration_min=62,
        point_progression=[[[0, 1], [1, 1]], [[1, 0]]],
    )
    r = api.get("/api/matches/1518158/statistics")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["team2_rallies_won"] == 50
    assert body["duration_min"] == 62
    assert len(body["point_progression"]) == 2


def test_analytics_tournament_gains(api):
    r = api.get("/api/analytics/tournament-gains?event=XD&min_matches=1&include_new=1")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    nets = [row["net_delta"] for row in results]
    assert nets == sorted(nets, reverse=True)
    top = results[0]
    assert {"player", "tournament", "net_delta", "matches", "mu_start"} <= set(top)
    # net_delta ≈ mu_end − mu_start
    assert abs(top["net_delta"] - (top["mu_end"] - top["mu_start"])) < 1.0


def test_perf_rating_solver():
    from apps.ingest.management.commands.build_analytics import _perf_rating

    # Beating two 2000-rated opponents => performance well above 2000.
    perf = _perf_rating([(2000.0, True), (2000.0, True)])
    assert perf > 2000
    # Split vs equal opponents => performance ≈ their level.
    even = _perf_rating([(1800.0, True), (1800.0, False)])
    assert abs(even - 1800) < 1
    # Beating a strong field scores higher than beating a weak one.
    strong = _perf_rating([(2200.0, True), (2100.0, True), (2000.0, True)])
    weak = _perf_rating([(1500.0, True), (1400.0, True), (1300.0, True)])
    assert strong > weak


def test_performance_path(api):
    pid = Match.objects.get(match_id=1518158).lineup.filter(side=2).first().player_id
    r = api.get(f"/api/performance/path?player={pid}&event=XD&tournament=5229")
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches
    m = matches[0]
    assert {"round_name", "won", "opponents", "score", "match_time_utc"} <= set(m)
    # ordered by round (earliest first)
    assert [x["round_order"] for x in matches] == sorted(x["round_order"] for x in matches)


def test_analytics_performances(api):
    r = api.get("/api/analytics/performances?event=XD&min_matches=1&include_new=1")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    perfs = [row["perf_rating"] for row in results]
    assert all(p is not None for p in perfs)
    assert perfs == sorted(perfs, reverse=True)


def test_max_comeback():
    from apps.ingest.h2h import max_comeback

    # Down 10-20, won 22-20 => overcame a 10-point deficit.
    prog = [[[i, min(i + 10, 20)] for i in range(0, 11)] + [[21, 20], [22, 20]]]
    assert max_comeback(prog) == 10
    # Wire-to-wire win => no deficit overcome.
    assert max_comeback([[[i, 0] for i in range(0, 22)]]) == 0
    assert max_comeback(None) is None


def test_records_endpoints(api):
    from apps.ingest.models import MatchStatistics

    m = Match.objects.filter(score_status="Normal").first()
    MatchStatistics.objects.create(
        match_id=m.match_id,
        team1_rallies_played=95, team2_rallies_played=95,
        duration_min=88,
        point_progression=[[[0, 5], [5, 5], [21, 18]]],  # side1 came from 5 down
        max_comeback=5,
    )
    for kind, field in [("longest", "duration_min"), ("rallies", "rallies"),
                        ("comebacks", "max_comeback")]:
        r = api.get(f"/api/records/{kind}?limit=10")
        assert r.status_code == 200
        rows = r.json()["results"]
        assert rows and rows[0]["match_id"] == m.match_id
        assert rows[0]["side1"] and rows[0]["side2"]
    # unknown kind rejected
    assert api.get("/api/records/nonsense").status_code == 400


def test_player_style(api):
    from apps.ingest.models import MatchStatistics

    m = Match.objects.filter(score_status="Normal", event="XD").first()
    MatchStatistics.objects.create(
        match_id=m.match_id, team1_rallies_played=80, team2_rallies_played=80,
        duration_min=50, point_progression=[[[21, 15]]],
    )
    pid = m.lineup.filter(side=1).first().player_id
    r = api.get(f"/api/players/{pid}/style")
    assert r.status_code == 200
    style = r.json()["style"]
    xd = next(s for s in style if s["event"] == "XD")
    assert xd["avg_rallies"] == 80 and xd["avg_duration"] == 50


def test_analytics_upsets(api):
    r = api.get("/api/analytics/upsets?event=XD&min_matches=1&include_new=1")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    best = [row["best_delta"] for row in results]
    assert best == sorted(best, reverse=True)
    assert results[0]["best_delta"] > 0
    # upsets are enriched with the round and the opponent(s) beaten
    assert "best_round" in results[0]
    assert "beat" in results[0]


def test_player_match_history_has_before_after(api):
    pid = Match.objects.get(match_id=1518158).lineup.filter(side=2).first().player_id
    r = api.get(f"/api/players/{pid}/matches")
    m = next(x for x in r.json()["results"] if x["match_id"] == 1518158)
    assert m["elo"] is not None
    assert {"before", "after", "delta"} <= set(m["elo"])


def test_cup_power(db):
    """Sudirman needs one active player/pair in each of MS/WS/MD/WD/XD."""
    from django.utils import timezone

    from apps.ingest.models import Partnership, Player, PlayerRating

    now = timezone.now()
    # Country CHN: singles for MS + WS; pairs for MD/WD/XD.
    ids = iter(range(1, 30))

    def player(cc):
        pid = next(ids)
        Player.objects.create(player_id=pid, name_display=f"P{pid}", country_code=cc)
        return pid

    for ev in ("MS", "WS"):
        PlayerRating.objects.create(
            player_id=player("CHN"), event=ev, mu=2400, rd=50, sigma=0.06,
            matches_played=30, last_match_utc=now,
        )
    for ev in ("MD", "WD", "XD"):
        a, b = player("CHN"), player("CHN")
        Partnership.objects.create(
            event=ev, player1_id=min(a, b), player2_id=max(a, b),
            matches_together=30, wins_together=25, combined_mu=2350,
            combined_rd=60, last_match_utc=now,
        )
    c = APIClient()
    body = c.get("/api/cups/sudirman").json()
    assert body["results"], "CHN can field a full Sudirman team"
    top = body["results"][0]
    assert top["country"] == "CHN"
    assert len(top["contributors"]) == 5  # one per discipline
    assert top["power"] > 0
    # bad cup name -> 400
    assert c.get("/api/cups/nope").status_code == 400


def test_cup_history_endpoint(api):
    r = api.get("/api/cups/thomas/history")
    assert r.status_code == 200
    body = r.json()
    assert {"cup", "years", "series"} <= set(body)


def test_retirement_rule(db):
    """A player idle > 1 year is hidden from CURRENT but kept in all-time peak."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.ingest.models import Player, PlayerRating

    now = timezone.now()
    Player.objects.create(player_id=1, name_display="Active")
    Player.objects.create(player_id=2, name_display="Retired")
    PlayerRating.objects.create(
        player_id=1, event="MS", mu=2000, rd=50, sigma=0.06, matches_played=20,
        last_match_utc=now, peak_mu=2000, peak_rd=50, peak_utc=now,
    )
    PlayerRating.objects.create(
        player_id=2, event="MS", mu=2500, rd=50, sigma=0.06, matches_played=20,
        last_match_utc=now - timedelta(days=800),
        peak_mu=2600, peak_rd=50, peak_utc=now - timedelta(days=800),
    )
    c = APIClient()
    cur = [r["player"]["player_id"] for r in c.get(
        "/api/leaderboard?event=MS&min_matches=1").json()["results"]]
    assert cur == [1]  # retired (id 2) excluded from current despite higher mu
    peak = [r["player"]["player_id"] for r in c.get(
        "/api/leaderboard?event=MS&min_matches=1&ranking=peak").json()["results"]]
    assert 2 in peak  # but present in all-time peak
    allc = [r["player"]["player_id"] for r in c.get(
        "/api/leaderboard?event=MS&min_matches=1&include_inactive=1").json()["results"]]
    assert set(allc) == {1, 2}


def test_events_endpoint(api):
    r = api.get("/api/events")
    assert r.status_code == 200
    rows = {row["event"]: row["rated_players"] for row in r.json()}
    assert rows["XD"] > 0
    assert rows["MS"] == 0  # only XD was ingested
