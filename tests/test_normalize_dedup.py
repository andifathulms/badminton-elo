"""Write-time contest de-duplication (root-cause guard in normalize_match).

A contest re-ingested under a second match_id — often the second copy without a
round label — must not create a duplicate that double-counts in ratings.
"""
import pytest

from apps.ingest.models import Match, Tournament
from apps.ingest.normalize import normalize_match
from apps.ingest.schemas import MatchRaw


def _tournament():
    return Tournament.objects.create(tournament_id=999001, name="Test Open", code="T1")


def _raw(match_id, round_name, p1=1, p2=2, score=((21, 15), (21, 10))):
    return MatchRaw.model_validate(
        {
            "id": match_id,
            "eventName": "MS",
            "roundName": round_name,
            "winner": 1,
            "scoreStatusValue": "Normal",
            "team1": {"players": [{"id": p1}]},
            "team2": {"players": [{"id": p2}]},
            "score": [{"home": h, "away": a} for h, a in score],
        }
    )


@pytest.mark.django_db
def test_blank_duplicate_is_skipped_keeping_labeled():
    t = _tournament()
    normalize_match(_raw(1000, "R16"), tournament=t, draw=None)
    # Same contest, different id, no round label -> must not create a second row.
    kept = normalize_match(_raw(2000, ""), tournament=t, draw=None)
    assert Match.objects.count() == 1
    assert kept.match_id == 1000 and kept.round_name == "R16"


@pytest.mark.django_db
def test_labeled_copy_replaces_earlier_blank():
    t = _tournament()
    normalize_match(_raw(3000, "", p1=5, p2=6), tournament=t, draw=None)
    kept = normalize_match(_raw(4000, "QF", p1=5, p2=6), tournament=t, draw=None)
    assert Match.objects.count() == 1
    assert kept.match_id == 4000 and kept.round_name == "QF"


@pytest.mark.django_db
def test_distinct_contests_are_not_merged():
    t = _tournament()
    normalize_match(_raw(5000, "SF", p1=1, p2=2, score=((21, 10),)), tournament=t, draw=None)
    # Same players but a genuinely different scoreline (a rematch) stays separate.
    normalize_match(_raw(5001, "Final", p1=1, p2=2, score=((19, 21), (21, 18))),
                    tournament=t, draw=None)
    assert Match.objects.count() == 2
