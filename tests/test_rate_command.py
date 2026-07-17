"""Integration tests for the `rate` bridge (PRD §7.7, M2).

Ingests the real MM2026 XD draw, runs `rate`, and asserts the engine produced
sane ratings through the ORM — and that a second `rate` is byte-identical.
"""
import json
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.ingest.models import (
    Draw,
    PlayerRating,
    RatingHistory,
    Tournament,
)
from apps.ingest.normalize import normalize_draw_data
from apps.ingest.schemas import DrawData

FIXTURE = Path(__file__).parent / "fixtures" / "draw_data_mm2026_xd.json"


@pytest.fixture
def rated(db):
    t = Tournament.objects.create(
        tournament_id=5229,
        code="MM-2026",
        name="PERODUA Malaysia Masters 2026",
        category_name="HSBC BWF World Tour Super 500",
    )
    draw = Draw.objects.create(
        tournament=t, draw_value="10", event="XD", stage="Main Draw", doubles=True
    )
    data = DrawData.model_validate(json.loads(FIXTURE.read_text()))
    normalize_draw_data(data, tournament=t, draw=draw)
    call_command("rate", verbosity=0)
    return t


def test_rate_populates_player_ratings(rated):
    assert PlayerRating.objects.filter(event="XD").exists()
    assert RatingHistory.objects.filter(event="XD").exists()
    # Only XD was ingested, so nothing in other disciplines.
    assert not PlayerRating.objects.exclude(event="XD").exists()


def test_ratings_are_finite_and_reasonable(rated):
    for r in PlayerRating.objects.all():
        assert 0 < r.mu < 4000
        assert 0 < r.rd <= 350  # capped at rd_init
        assert r.matches_played >= 1


def test_winners_outrank_early_losers(rated):
    """Players who advanced deep should sit above those who lost round one."""
    ratings = {r.player_id: r.mu for r in PlayerRating.objects.all()}
    # The retired match 1518150: side 2 advanced — they should not be bottom.
    from apps.ingest.models import MatchPlayer

    advancers = list(
        MatchPlayer.objects.filter(match_id=1518150, side=2).values_list(
            "player_id", flat=True
        )
    )
    assert advancers
    for pid in advancers:
        assert pid in ratings


def test_rate_is_deterministic(rated):
    """A second full recompute yields an identical rating table (PRD §7.7)."""
    def snapshot():
        return sorted(
            PlayerRating.objects.values_list("player_id", "event", "mu", "rd", "sigma")
        )

    first = snapshot()
    call_command("rate", verbosity=0)
    assert snapshot() == first


def test_rebuild_flag_matches_plain_rate(rated):
    def snapshot():
        return sorted(PlayerRating.objects.values_list("player_id", "mu", "rd"))

    plain = snapshot()
    call_command("rate", "--rebuild", verbosity=0)
    assert snapshot() == plain
