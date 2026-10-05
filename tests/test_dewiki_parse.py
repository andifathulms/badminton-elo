"""German Wikipedia match-list parser (pre-2006 backfill)."""
from collections import Counter

from apps.ingest.dewiki_parse import parse_article, start_date
from apps.ingest.management.commands.scrape_dewiki import scoring_code, tier_of, wanted

ARTICLE = """Die '''Example Open 1995''' fanden vom 10. bis zum 16. Juli 1995 in [[Jakarta]] statt.

== Sieger und Platzierte ==
* {{IDN|#}} [[Ardy Wiranata]] – {{IDN|#}} [[Joko Suprianto]]: 15-7 / 15-9
== Herreneinzel ==
=== Setzliste ===
# {{IDN|#}} [[Ardy Wiranata]]
=== Qualifikation ===
* {{NLD|#}} [[Q One]] – {{FIN|#}} [[Q Two]]: w.o.
=== Hauptrunde ===
* {{IDN|#}} [[Ardy Wiranata]] – {{ENG|#}} [[P1]]: 15-1 / 15-2
* {{IDN|#}} [[Joko Suprianto]] – {{DNK|#}} [[P2]]: 15-11 / 4-15 / 15-12
* {{DNK|#}} [[P3]] – {{SWE|#}} [[P4]]: 15-3 / 2-1 aufg.
* {{IDN|#}} [[Alan Budikusuma]] – {{CHN|#}} [[P5]]: 15-8 / 15-8
* {{IDN|#}} [[Ardy Wiranata]] – {{IDN|#}} [[Joko Suprianto]]: 15-10 / 15-6
* {{IDN|#}} [[Alan Budikusuma]] – {{DNK|#}} [[P3]]: 15-5 / 15-5
* {{IDN|#}} [[Ardy Wiranata]] – {{IDN|#}} [[Alan Budikusuma]]: 15-12 / 15-13
== Herrendoppel ==
* {{IDN|#}} [[Rudy Gunawan]] / {{IDN|#}} [[Bambang Suprianto]] – {{KOR|#}} [[A]] / {{KOR|#}} [[B]]: 15-5 / 15-5
== Weblinks ==
* [https://example.org tournamentsoftware.com]
"""


def test_parses_sections_rounds_and_statuses():
    ms = parse_article(ARTICLE)
    ms_main = [m for m in ms if m["event"] == "MS" and m["stage"] == "main"]
    assert Counter(m["round_name"] for m in ms_main) == {"QF": 4, "SF": 2, "F": 1}
    final = next(m for m in ms_main if m["round_name"] == "F")
    assert [p[1] for p in final["side1"]] == ["Ardy Wiranata"] and final["winner_side"] == 1
    qual = [m for m in ms if m["stage"] == "qual"]
    assert qual[0]["status"] == "Walkover" and qual[0]["round_name"] == "Q1"
    retired = next(m for m in ms_main if m["side1"][0][1] == "P3" and m["round_name"] == "QF")
    assert retired["status"] == "Retired" and retired["games"] == [(15, 3), (2, 1)]
    md = [m for m in ms if m["event"] == "MD"]
    assert len(md) == 1 and md[0]["side1"][0][2] == "IDN" and len(md[0]["side2"]) == 2
    # The medal table and the Weblinks list are not matches.
    assert len(ms) == 9


def test_lead_date_and_filters():
    assert str(start_date(ARTICLE, 1995)) == "1995-07-10"
    assert wanted("Indonesia Open 1995") and wanted("Badminton-Europameisterschaft 1990")
    assert not wanted("Dänische Badmintonmeisterschaft 1995")
    assert not wanted("Badminton-Bundesliga 1994/95") and not wanted("German Juniors 1995")
    assert wanted("Nordische Badmintonmeisterschaft 1995")
    assert tier_of("All England 1985", set()) == "All England"
    assert tier_of("Denmark Open 1995", {"Denmark Open 1995"}) == "Grand Prix"


def test_side_out_scoring_codes():
    assert scoring_code([(15, 3), (15, 7)]) == "15x3s"
    assert scoring_code([(7, 3), (7, 5), (7, 1)]) == "5x7"


def test_side_out_relabelling_rule():
    from apps.ingest.management.commands.fix_scoring_formats import side_out_code
    from apps.ingest.management.commands.scrape_wiki import scoring_format

    assert side_out_code([15, 17]) == "15x3s"      # setting to 17
    assert side_out_code([11, 13, 11]) == "15x3s"  # women's singles to 11
    assert side_out_code([7, 7, 9]) == "5x7"
    assert side_out_code([21, 19]) is None         # rally, leave it
    assert scoring_format([(15, 4), (15, 9)], 1995) == "15x3s"
    assert scoring_format([(15, 4), (15, 9)], 2016) == "3x15"


def test_byes_are_not_matches():
    text = "== Herreneinzel ==\n* {{DNK|#}} [[Peter Gade]] – Freilos: w.o.\n* {{DNK|#}} [[A]] – Bye: w.o.\n"
    assert parse_article(text) == []


FINALS = """Die Japan Open 1984 fanden vom 19. bis zum 22. Januar 1984 statt.
== Finalergebnisse ==
{| class=wikitable
! Disziplin
! Sieger
! Finalist
! Ergebnis
|-
| Herreneinzel
| {{DNK|#}} [[Morten Frost]]
| {{IDN|#}} [[Liem Swie King]]
| 15-1, 18-15
|-
| Dameneinzel
| {{ENG|#}} [[Karen Bridge|Karen Beckman]]<br />{{ENG|#}} [[Gillian Gilks]]
| {{IDN|#}} [[Ruth Damayanti]]<br />{{IDN|#}} [[Verawaty Fadjrin]]
| 13-15, 15-3, 15-12
|-
| rowspan="2"| Dameneinzel
| {{CHN|#}} [[Qian Ping]]
| {{CHN|#}} [[Zheng Yuli]]
| 3-1, Aufgabe
|}
"""


def test_finals_table_fills_events_without_match_lists():
    ms = {m["event"]: m for m in parse_article(FINALS)}
    assert ms["MS"]["games"] == [(15, 1), (18, 15)]
    assert ms["MS"]["round_name"] == "F"
    # a two-player row under a singles label is the doubles final
    assert [p[1] for p in ms["WD"]["side1"]] == ["Karen Beckman", "Gillian Gilks"]
    assert ms["WS"]["status"] == "Retired"


def test_finals_table_never_duplicates_a_match_list():
    text = "== Herreneinzel ==\n* [[A]] – [[B]]: 15-1 / 15-2\n" + FINALS
    ms = parse_article(text)
    assert [m["event"] for m in ms].count("MS") == 1
