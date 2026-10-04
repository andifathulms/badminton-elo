"""Cross-source duplicate tournaments and bye clean-up."""
from datetime import date

import pytest
from django.core.management import call_command

from apps.ingest.models import Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.wiki_parse import is_bye


def _t(tid, name, code=None):
    return Tournament.objects.create(tournament_id=tid, name=name, code=code,
                                     start_date=date(2023, 5, 14), match_count=1)


def _m(mid, t, p1, p2, games, event="MS", winner=1):
    m = Match.objects.create(match_id=mid, tournament=t, event=event, round_name="R1",
                             score_status="Normal", winner_side=winner)
    MatchPlayer.objects.create(match=m, side=1, player=p1)
    MatchPlayer.objects.create(match=m, side=2, player=p2)
    for i, (a, b) in enumerate(games, 1):
        Game.objects.create(match=m, game_no=i, side1_points=a, side2_points=b)
    return m


@pytest.mark.parametrize("text,bye", [
    ("Bye", True), ("bye<br/>bye", True), ("''Bye''", True),
    ("[[Bye (sports)|Bye]]", True), ("Lin Dan", False), ("Byer Smith", False),
])
def test_is_bye(text, bye):
    assert is_bye(text) is bye


@pytest.mark.django_db
def test_wiki_copy_merges_into_api_tournament():
    api = _t(1, "Sudirman Cup 2023")
    wiki = _t(2_000_000_900, "2023 Sudirman Cup", code="wiki:2023 Sudirman Cup")
    a, b, c, d = (Player.objects.create(player_id=i, name_display=n)
                  for i, n in ((1, "Viktor AXELSEN"), (2, "LOH Kean Yew"), (3, "Kento MOMOTA"),
                               (4, "Lee Zii Jia")))
    wa = Player.objects.create(player_id=2_000_000_001, name_display="Viktor Axelsen")
    wb = Player.objects.create(player_id=2_000_000_002, name_display="Loh Kean Yew")
    for i in range(10):  # ten contests in both copies (same scores)
        _m(10 + i, api, a, b, [(21, 10 + i), (21, 12)])
        _m(2_000_000_100 + i, wiki, wa, wb, [(21, 10 + i), (21, 12)])
    _m(2_000_000_200, wiki, c, d, [(21, 19), (21, 17)])      # only on Wikipedia: kept
    _m(2_000_000_201, wiki, c, d, [(1, 2)])                   # a set count, not points
    Tournament.objects.update(match_count=1)

    call_command("dedup_tournaments", "--apply", verbosity=0)

    assert not Tournament.objects.filter(pk=wiki.pk).exists()
    assert Match.objects.filter(tournament=api).count() == 11
    assert Match.objects.filter(pk=2_000_000_200, tournament=api).exists()
    assert not Match.objects.filter(pk=2_000_000_201).exists()


@pytest.mark.django_db
def test_purge_byes_removes_pseudo_matches_and_players():
    t = _t(5, "Old Open", code="wiki:Old Open")
    p = Player.objects.create(player_id=7, name_display="Lin Dan")
    bye = Player.objects.create(player_id=8, name_display="[[Bye (sports)|Bye]]")
    _m(70, t, p, bye, [])
    call_command("purge_byes", "--apply", verbosity=0)
    assert not Match.objects.filter(pk=70).exists()
    assert not Player.objects.filter(pk=8).exists() and Player.objects.filter(pk=7).exists()


@pytest.mark.parametrize("label,gender", [
    ("Uber Cup - Group A", "W"), ("Thomas Cup - Play-Off", "M"),
    ("Women's Team - Group B", "W"), ("Men's Team - All Africa Men's & Women's", "M"),
    ("Female Cup - Final", "W"),
])
def test_team_draw_gender(label, gender):
    from apps.ingest.management.commands.scrape_bwf_team import _gender_of

    assert _gender_of(label) == gender


@pytest.mark.django_db
def test_gender_is_the_majority_of_appearances():
    t = _t(9, "Open")
    lin = Player.objects.create(player_id=1, name_display="Lin Dan")
    opp = Player.objects.create(player_id=2, name_display="Opp")
    for i in range(5):
        _m(100 + i, t, lin, opp, [(21, 10)], event="MS")
    _m(200, t, lin, opp, [(21, 10)], event="WS")  # one mislabelled rubber
    call_command("infer_gender", verbosity=0)
    assert Player.objects.get(pk=1).gender == "M"


@pytest.mark.django_db
def test_fix_cup_events_keeps_age_group_labels():
    t = _t(10, "World Senior Team Championships")
    a = Player.objects.create(player_id=1, name_display="A", gender="M")
    b = Player.objects.create(player_id=2, name_display="B", gender="M")
    _m(300, t, a, b, [(21, 10)], event="MS45")
    _m(301, t, a, b, [(21, 10)], event="WS")
    call_command("fix_cup_events", verbosity=0)
    assert Match.objects.get(pk=300).event == "MS45"
    assert Match.objects.get(pk=301).event == "MS"


def test_european_acronym_draws_are_gendered():
    from apps.ingest.management.commands.scrape_bwf_team import _gender_of

    assert _gender_of("2018 EWTC - Group 1") == "W"
    assert _gender_of("2018 EMTC - Group 1") == "M"


@pytest.mark.django_db
def test_fix_team_splits_moves_rubbers_to_the_right_gender():
    men = Tournament.objects.create(tournament_id=11, name="Euro TC – Men's team",
                                    code="GUID-1:M", start_date=date(2018, 2, 13))
    a = Player.objects.create(player_id=1, name_display="A", gender="F")
    b = Player.objects.create(player_id=2, name_display="B", gender="F")
    _m(400, men, a, b, [(21, 10)], event="WS")
    call_command("fix_team_splits", "--apply", verbosity=0)
    women = Tournament.objects.get(code="GUID-1:W")
    assert Match.objects.get(pk=400).tournament_id == women.tournament_id
    assert "Women's" in women.name


@pytest.mark.parametrize("name,suffix", [
    ("BWF World Junior Championships 2017", "U19"),
    ("BABOLAT French U17 International 2019", "U17"),
    ("Jakarta Open Junior International 2016 (U17 & U15)", "U17"),
    ("YONEX All England Open 2026", ""),
])
def test_tournament_youth(name, suffix):
    from apps.ingest.management.commands.normalize_events import tournament_youth

    assert tournament_youth(name) == suffix


@pytest.mark.django_db
def test_wiki_superset_drops_only_the_api_rubbers_it_contains():
    api = _t(20, "Asian Games 2022 (Team Event) – Men's team")
    wiki = _t(2_000_000_950, "Badminton at the 2022 Asian Games",
              code="wiki:Badminton at the 2022 Asian Games")
    ps = [Player.objects.create(player_id=i, name_display=f"Player {chr(65 + i)}") for i in range(1, 9)]
    for i in range(4):  # 4 team rubbers in both
        _m(500 + i, api, ps[0], ps[1], [(21, 10 + i), (21, 9)])
        _m(2_000_000_500 + i, wiki, ps[0], ps[1], [(21, 10 + i), (21, 9)])
    for i in range(10):  # 10 individual matches only on Wikipedia
        _m(2_000_000_600 + i, wiki, ps[2 + i % 3], ps[5 + i % 3], [(21, 3 + i), (21, 4)])
    call_command("dedup_tournaments", "--apply", verbosity=0)
    assert Match.objects.filter(tournament=wiki).count() == 10
    assert Match.objects.filter(tournament=api).count() == 4
