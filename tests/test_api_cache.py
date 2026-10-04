"""Versioned API response cache + DataVersion bumps."""
import pytest
from django.core.cache import caches
from django.core.management import call_command

from apps.ingest.dataversion import bump, current
from apps.ingest.models import Player, PlayerRating


@pytest.fixture(autouse=True)
def clear_cache():
    caches["api"].clear()
    yield
    caches["api"].clear()


@pytest.fixture
def board(db):
    p = Player.objects.create(player_id=1, name_display="A")
    PlayerRating.objects.create(player=p, event="MS", mu=1600, rd=60, sigma=0.06,
                                matches_played=9)
    return p


URL = "/api/leaderboard?event=MS&include_inactive=1"


def test_second_get_is_served_from_cache(client, board):
    r1 = client.get(URL)
    r2 = client.get(URL)
    assert r1["X-Cache"] == "miss" and r2["X-Cache"] == "hit"
    assert r1.content == r2.content
    assert r1["ETag"] == r2["ETag"]


def test_matching_etag_gets_304(client, board):
    etag = client.get(URL)["ETag"]
    r = client.get(URL, HTTP_IF_NONE_MATCH=etag)
    assert r.status_code == 304


def test_bump_invalidates_everything(client, board):
    etag = client.get(URL)["ETag"]
    PlayerRating.objects.filter(player=board).update(mu=1700)
    bump()
    r = client.get(URL, HTTP_IF_NONE_MATCH=etag)
    assert r.status_code == 200 and r["X-Cache"] == "miss"
    assert r.json()["results"][0]["mu"] == 1700


def test_query_order_does_not_split_the_cache(client, board):
    client.get("/api/leaderboard?event=MS&include_inactive=1")
    r = client.get("/api/leaderboard?include_inactive=1&event=MS")
    assert r["X-Cache"] == "hit"


def test_staff_and_auth_endpoints_are_not_cached(client, db):
    r = client.get("/api/auth/me")
    assert "X-Cache" not in r


def test_data_commands_bump_the_version(db, board):
    before = current().version
    call_command("build_consistency", verbosity=0)
    assert current().version != before


def test_active_cutoff_comes_from_version(db, board):
    from datetime import datetime, timedelta, timezone

    t = datetime(2026, 3, 1, tzinfo=timezone.utc)
    PlayerRating.objects.update(last_match_utc=t)
    assert bump().active_cutoff == t - timedelta(days=365)
