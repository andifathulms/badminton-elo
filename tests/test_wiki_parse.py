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


BOLD = """
{{8TeamBracket-Tennis3
| RD1-team1='''{{flagicon|China}} [[Lin Dan]]'''
| RD1-score1-1=5
| RD1-score1-2='''15'''
| RD1-score1-3='''15'''
| RD1-team2={{flagicon|South Korea}} [[Lee Hyun-il]]
| RD1-score2-1='''15'''
| RD1-score2-2=7
| RD1-score2-3=8
}}
"""


def test_bold_scores_and_fullname_flags():
    # bold '''15''' must parse as 15 (not 0), so Lin Dan wins; full-name flag ->code
    ms = wiki_parse.parse_bracket(BOLD, "MS")
    assert len(ms) == 1
    m = ms[0]
    assert m["side1"]["country"] == "CHN"
    assert m["side2"]["country"] == "KOR"
    assert m["games"] == [(5, 15), (15, 7), (15, 8)]
    assert m["winner_side"] == 1  # Lin Dan wins 2-1


def test_multiple_brackets_not_merged():
    # two templates in one text must not bleed params into each other
    two = BRACKET + "\n" + BRACKET.replace("Zhao Jianhua", "Morten Frost")
    ms = wiki_parse.parse_bracket(two, "MS")
    names = {p[0] for m in ms for p in m["side1"]["players"] + m["side2"]["players"]}
    assert "Morten Frost" in names and "Zhao Jianhua" in names


def test_trim_clinched_drops_spurious_third_game():
    assert wiki_parse._trim_clinched([(15, 3), (15, 7), (3, 0)]) == [(15, 3), (15, 7)]
    # a genuine 3-gamer is kept
    assert wiki_parse._trim_clinched([(15, 10), (10, 15), (15, 12)]) == \
        [(15, 10), (10, 15), (15, 12)]


TIE = """
===China vs Denmark===
{{Badmintonbox
|team1=China
|team2=Denmark
|score1=3
|score2=1
|R1={{ BadmintonMatch |T1P1=[[Lin Dan]] |15 |15 | |T2P1=[[Peter Gade]] |8 |13 | }}
|R2={{ BadmintonMatch |T1P1=[[Cai Yun]] |T1P2=[[Fu Haifeng]] |16 |6 | |T2P1=[[Lars Paaske]] |T2P2=[[Jonas Rasmussen]] |17 |15 | }}
|R5={{ BadmintonMatch |T1P1=[[Bao Chunlai]] | | | |T2P1=[[Kenneth Jonassen]] | | | |np=}}
}}
"""


def test_team_tie_rubbers():
    ms = wiki_parse.parse_team_ties(TIE, "thomas")
    # R5 is np (not played) -> dropped; R1 singles, R2 doubles
    assert len(ms) == 2
    singles = next(m for m in ms if len(m["side1"]["players"]) == 1)
    doubles = next(m for m in ms if len(m["side1"]["players"]) == 2)
    assert singles["event"] == "MS" and doubles["event"] == "MD"
    # Lin Dan beat Peter Gade 15-8 15-13
    assert _names(singles["side1"]) == ["Lin Dan"]
    assert singles["games"] == [(15, 8), (15, 13)]
    assert singles["winner_side"] == 1
    assert singles["side1"]["country"] == "CHN"
    # doubles: Danes won 17-16 15-6 -> side2
    assert doubles["winner_side"] == 2


def test_team_tie_sudirman_event_by_slot():
    tie = TIE.replace("|R1=", "|R3=")  # R3 -> MD in Sudirman order
    ms = wiki_parse.parse_team_ties(tie, "sudirman")
    md = next(m for m in ms if len(m["side1"]["players"]) == 1)  # was R3 singles
    assert md["event"] == "MD"  # Sudirman R3 slot = MD regardless of singles/doubles


def test_scoreless_final_still_parsed():
    txt = FINALS.replace("15–4, 15–1", "walkover")
    finals = wiki_parse.parse_final_table(txt)
    ms = next(m for m in finals if m["event"] == "MS")
    assert ms["games"] == []
    assert ms["retired"] is True


# Real brackets leave every unused game cell empty (game 3-5, byes, and the
# whole first round for a seed). The param regex must NOT let an empty value
# swallow the following line — a bug that mis-paired teams and produced garbage
# scores like (1, 20), (0, 21) and flipped winners.
EMPTY_CELLS = """
{{16TeamBracket-Compact-Tennis3
| RD1=First Round
| RD2=Second Round
| RD1-team01={{Flagicon|CHN}} '''[[Zhang Ning]]'''
| RD1-seed01=1
| RD1-score01-1=
| RD1-score01-2=
| RD1-score01-3=
| RD1-team02=[[Bye (sports)|Bye]]
| RD1-score02-1=
| RD1-score02-2=
| RD1-team03={{Flagicon|NZL}} [[Rachel Hindley]]
| RD1-score03-1='''22'''
| RD1-score03-2=16
| RD1-score03-3=12
| RD1-team04={{Flagicon|SIN}} '''[[Xing Aiying]]'''
| RD1-score04-1=20
| RD1-score04-2='''21'''
| RD1-score04-3='''21'''
| RD2-team01={{Flagicon|CHN}} '''[[Zhang Ning|Zhang]]'''
| RD2-seed01=1
| RD2-score01-1='''21'''
| RD2-score01-2='''21'''
| RD2-score01-3=
| RD2-team02={{Flagicon|SIN}} [[Xing Aiying|Xing]]
| RD2-score02-1=8
| RD2-score02-2=8
| RD2-score02-3=
}}
"""


def test_empty_score_cells_do_not_swallow_next_line():
    ms = wiki_parse.parse_bracket(EMPTY_CELLS, "WS")
    # Zhang's first-round bye is not a real match (opponent is a bye placeholder)
    assert all("Bye" not in _names(m["side1"]) + _names(m["side2"]) for m in ms)
    # First round: Rachel Hindley lost to Xing Aiying 22-20, 16-21, 12-21
    rx = next(m for m in ms if "Rachel Hindley" in _names(m["side1"]) + _names(m["side2"]))
    assert rx["games"] == [(22, 20), (16, 21), (12, 21)]
    assert rx["winner_side"] == 2
    # Second round: Zhang beat Xing 21-8, 21-8 (winner NOT flipped)
    zx = next(m for m in ms if m["round_label"] == "Second Round")
    assert zx["games"] == [(21, 8), (21, 8)]
    assert zx["winner_side"] == 1
    assert _names(zx["side1"]) == ["Zhang Ning"]
