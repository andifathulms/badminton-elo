"""Unit tests for the normalization helpers (PRD §6) — no DB needed."""
from datetime import date

from apps.ingest import normalize as n


def test_round_order_canonical_and_aliases():
    assert n.round_order("R32") == 3
    assert n.round_order("Final") == 7
    assert n.round_order("Quarter Finals") == 5  # alias
    assert n.round_order("weird") == 0  # unknown -> 0


def test_scoring_format_date_defaults():
    assert n.default_scoring_format(date(2026, 5, 24)) == "3x21"
    assert n.default_scoring_format(date(2027, 1, 4)) == "3x15"
    assert n.default_scoring_format(None) == ""


def test_status_map_excludes_non_counting():
    assert n.map_status("Normal") == ("Normal", False)
    assert n.map_status("Retired") == ("Retired", False)
    assert n.map_status("Walkover")[1] is True  # rating-excluded
    # Unknown -> excluded, keeps the raw label for inspection.
    label, excluded = n.map_status("SomethingNew")
    assert excluded is True and label == "SomethingNew"
