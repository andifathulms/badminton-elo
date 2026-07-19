"""Tests for the Wikipedia bracket parser (pure, no network/Django)."""
from apps.ingest import wiki_parse


BRACKET = """
{{16TeamBracket-Compact-Tennis3
| RD1=Round of 16
| RD2=Quarter-finals
| RD3=Semi-finals
| RD1-team01={{flagicon|CHN}} [[Zhao Jianhua]]
| RD1-team02={{flagicon|DEN}} [[Thomas Kirkegaard]]
| RD1-score01-1=15
| RD1-score02-1=3
| RD1-score01-2=15
| RD1-score02-2=6
| RD1-team03={{flagicon|INA}} [[Alan Budikusuma]]
| RD1-team04={{flagicon|DEN}} [[Torben Carlsen]]
| RD1-score03-1=15
| RD1-score04-1=12
| RD1-score03-2=15
| RD1-score04-2=6
| RD2-team01={{flagicon|CHN}} [[Zhao Jianhua]]
| RD2-team02={{flagicon|INA}} [[Alan Budikusuma]]
| RD2-score01-1=15
| RD2-score02-1=10
| RD2-score01-2=15
| RD2-score02-2=8
}}
"""

FINALS = """
==Final results==
{| class=wikitable
!Category!!Winners!!Runners-up!!Score
|-
|Men's singles
| {{flagicon|CHN}} [[Zhao Jianhua]]
| {{flagicon|INA}} [[Joko Suprianto]]
| 15–4, 15–1
|-
|Women's doubles
| {{flagicon|KOR}} [[Chung Myung-hee]] & [[Hwang Hye-young]]
| {{flagicon|ENG}} [[Gillian Clark (badminton)|Gillian Clark]] & [[Gillian Gowers]]
| 6–15, 15–4, 15–4
|}
"""


def _names(team):
    return sorted(p[0] for p in team["players"])


def test_bracket_pairs_and_winners():
    ms = wiki_parse.parse_bracket(BRACKET, "MS")
    # 2 first-round + 1 semi = 3 matches
    assert len(ms) == 3
    r1 = [m for m in ms if m["round_label"] == "Round of 16"]
    assert len(r1) == 2
    zhao = next(m for m in ms if m["round_label"] == "Quarter-finals")
    # Zhao (side1) beat Budikusuma 15-10 15-8
    assert zhao["winner_side"] == 1
    assert zhao["games"] == [(15, 10), (15, 8)]
    assert _names(zhao["side1"]) == ["Zhao Jianhua"]


def test_country_and_advancement():
    ms = wiki_parse.parse_bracket(BRACKET, "MS")
    m = ms[0]
    assert m["side1"]["country"] == "CHN"
    assert m["winner_side"] == 1  # Zhao won 15-3 15-6


def test_finals_table_all_disciplines():
    finals = wiki_parse.parse_final_table(FINALS)
    ev = {m["event"]: m for m in finals}
    assert set(ev) == {"MS", "WD"}
    assert ev["MS"]["winner_side"] == 1
    assert ev["MS"]["games"] == [(15, 4), (15, 1)]
    # doubles: two players parsed per side
    assert _names(ev["WD"]["side1"]) == ["Chung Myung-hee", "Hwang Hye-young"]
    assert ev["WD"]["games"] == [(6, 15), (15, 4), (15, 4)]


def test_womens_not_matched_as_mens():
    # "women's singles" must not be read as "men's singles"
    text = "==Women's singles==\n===Section 1===\n" + BRACKET
    matches = wiki_parse.parse_article(text)
    assert matches and all(m["event"] == "WS" for m in matches)


def test_scoreless_final_still_parsed():
    txt = FINALS.replace("15–4, 15–1", "walkover")
    finals = wiki_parse.parse_final_table(txt)
    ms = next(m for m in finals if m["event"] == "MS")
    assert ms["games"] == []
    assert ms["retired"] is True
