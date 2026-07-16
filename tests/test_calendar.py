"""Calendar enumeration tests against the REAL captured 2026 season payload."""
import json
from pathlib import Path

import pytest

from apps.ingest.models import Match, Tournament
from apps.ingest.normalize import (
    synthetic_tournament_id,
    upsert_tournament_from_calendar,
    upsert_tournament_from_code,
)
from apps.ingest.schemas import GroupedYearTournaments

FIXTURE = Path(__file__).parent / "fixtures" / "grouped_year_tournaments_2026.json"
MM_CODE = "71AC3AB2-C072-444C-B479-4AC73C756C14"
MM_ID = 5229


def _calendar():
    return GroupedYearTournaments.model_validate(json.loads(FIXTURE.read_text()))


def test_calendar_enumerates_full_season():
    tours = _calendar().all_tournaments()
    assert len(tours) == 30
    # every entry has a real id, code, and tier
    assert all(t.id and t.code and t.category for t in tours)


def test_calendar_entry_carries_tier_and_dates():
    mm = next(t for t in _calendar().all_tournaments() if t.code == MM_CODE)
    assert mm.id == MM_ID
    assert mm.category == "HSBC BWF World Tour Super 500"
    assert str(mm.start) == "2026-05-19" and str(mm.end) == "2026-05-24"
    assert mm.prize_money_decimal == 500000


def test_upsert_from_calendar_uses_real_id(db):
    mm = next(t for t in _calendar().all_tournaments() if t.code == MM_CODE)
    t = upsert_tournament_from_calendar(mm)
    assert t.tournament_id == MM_ID
    assert t.category_name == "HSBC BWF World Tour Super 500"
    assert t.start_date.isoformat() == "2026-05-19"


def test_calendar_reconciles_synthetic_row_and_keeps_matches(db):
    """A day-matches-only run creates a synthetic-id row; the calendar upsert
    must migrate its matches onto the real id and drop the stale row."""
    # 1) simulate the day-matches-first path
    synth = upsert_tournament_from_code(MM_CODE, "PERODUA Malaysia Masters 2026")
    assert synth.tournament_id == synthetic_tournament_id(MM_CODE)
    Match.objects.create(
        match_id=999001,
        tournament=synth,
        event="XD",
        round_name="Final",
        score_status="Normal",
        winner_side=1,
    )

    # 2) calendar upsert reconciles
    mm = next(t for t in _calendar().all_tournaments() if t.code == MM_CODE)
    real = upsert_tournament_from_calendar(mm)

    assert real.tournament_id == MM_ID
    assert not Tournament.objects.filter(tournament_id=synth.tournament_id).exists()
    assert Tournament.objects.filter(code=MM_CODE).count() == 1
    # the match followed to the real id
    assert Match.objects.get(match_id=999001).tournament_id == MM_ID
