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
