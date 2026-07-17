"""Tests for event canonicalization (folds BWF's inconsistent discipline labels)."""
import pytest

from apps.ingest.normalize import canonical_event


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MS", "MS"), ("WS", "WS"), ("MD", "MD"), ("WD", "WD"), ("XD", "XD"),
        # English spelling/case variants
        ("Mens Singles", "MS"),
        ("Men's Singles", "MS"),
        ("Men's singles", "MS"),
        ("MEN'S SINGLES", "MS"),
        ("Men's Single", "MS"),
        ("ms", "MS"),
        ("Womens Singles", "WS"),
        ("Women's Doubles", "WD"),
        ("Mens Doubles", "MD"),
        ("Mixed Doubles", "XD"),
        ("Mixed doubles", "XD"),
        # women must not be misread as men (substring trap)
        ("WOMEN'S SINGLES", "WS"),
        ("Women's singles", "WS"),
        # sponsor-prefixed real events
        ("Hayes Knight Mens Singles", "MS"),
        ("Bank of New Zealand Mens Doubles", "MD"),
        # other languages
        ("Individual Masculino", "MS"),
        ("Individual Femenino", "WS"),
        ("Dobles Mixtos", "XD"),
        ("Dobles Masculinos", "MD"),
        ("MX", "XD"),
    ],
)
def test_folds_to_open_disciplines(raw, expected):
    code, exhibition = canonical_event(raw)
    assert code == expected
    assert exhibition is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MS 45", "MS45"),
        ("MD 40", "MD40"),
        ("XD 55", "XD55"),
        ("WS 70", "WS70"),
    ],
)
def test_masters_keep_distinct_age_bucket(raw, expected):
    assert canonical_event(raw)[0] == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MS-U19", "MSU19"),
        ("BS U15", "MSU15"),  # boys singles -> male youth bucket
        ("GS U17", "WSU17"),  # girls singles -> female youth bucket
        ("WD-U19", "WDU19"),
    ],
)
def test_youth_keep_distinct_bucket(raw, expected):
    assert canonical_event(raw)[0] == expected


@pytest.mark.parametrize(
    "raw,base",
    [
        ("MD Exhibition", "MD"),
        ("Mens Singles Plate", "MS"),
    ],
)
def test_exhibitions_flagged_for_exclusion(raw, base):
    code, exhibition = canonical_event(raw)
    assert code == base
    assert exhibition is True


def test_unmappable_passes_through():
    # Ambiguous 2-letter foreign codes stay as-is (won't pollute the open pools).
    assert canonical_event("HE") == ("HE", False)
    assert canonical_event("") == ("", False)


def test_masters_and_youth_do_not_pollute_open_pools():
    assert canonical_event("MS 45")[0] != "MS"
    assert canonical_event("MS-U19")[0] != "MS"
