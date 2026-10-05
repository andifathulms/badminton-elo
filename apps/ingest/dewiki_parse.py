"""Parse German Wikipedia badminton tournament articles (pre-2006 backfill).

English Wikipedia often has only the finals of a 1983-2005 event; German
Wikipedia lists every match, qualifying included, one per line, winner first:

    == Herreneinzel ==
    === Qualifikation ===
    * {{DNK|#}} [[Peter Gade]] – {{ISL|#}} [[Tryggvi Nielsen]]: 15-1 / 15-1
    * {{IDN|#}} [[A]] / {{IDN|#}} [[B]] – {{KOR|#}} [[C]] / {{KOR|#}} [[D]]: w.o.

Richer articles draw the later rounds as German bracket templates
({{Turnierplan16-kompakt-3}}, {{Turnierplan4-3}}) — same RDn-teamNN /
RDn-scoreNN-g parameters as English brackets, parsed by wiki_parse and merged
in page order with the list lines.

Rounds are not labelled consistently, so they are rebuilt from the bracket
itself: a match's depth is one more than that of the next match its winner
plays (the final is depth 0), which stays right with byes. Qualifying rounds
are numbered forward (Q1, Q2, ...). Pure: text in, dicts out.
"""
from __future__ import annotations

import math
import re
from datetime import date

from .wiki_parse import _parse_one, _template_body, is_bye

DISCIPLINES = [  # (heading word, event) — longest first
    ("herreneinzel", "MS"), ("dameneinzel", "WS"), ("herrendoppel", "MD"),
    ("damendoppel", "WD"), ("gemischtes doppel", "XD"), ("mixed", "XD"),
]
QUAL = re.compile(r"qualifikation", re.I)
HEADING = re.compile(r"^(=+)\s*(.+?)\s*=+\s*$")
LINE = re.compile(r"^\*\s*(?P<s1>.+?)\s+[–—]\s+(?P<s2>.+?):\s*(?P<score>.+?)\s*$")
LINK = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|\s*([^\]]+?)\s*)?\]\]")
FLAG = re.compile(r"\{\{\s*([A-Z]{2,3}(?:-[A-Z]{2})?)\s*\|")
GAME = re.compile(r"(\d{1,2})\s*[-:–]\s*(\d{1,2})")
WALKOVER = re.compile(r"\bw\.?\s*o\.?\b|kampflos|walkover", re.I)
RETIRED = re.compile(r"aufg|ret\.?|zurück", re.I)
MONTHS = {m: i for i, m in enumerate(
    ["", "januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
     "september", "oktober", "november", "dezember"])}
LEAD_DATE = re.compile(
    r"(\d{1,2})\.\s*(?:(?:bis\s*(?:zum\s*)?)?\d{1,2}\.\s*)?"
    r"(" + "|".join(m for m in MONTHS if m) + r")\s*(\d{4})", re.I)
TURNIERPLAN = re.compile(r"\{\{\s*Turnierplan(\d+)", re.I)
TABLE = re.compile(r"\{\|(.*?)\n\|\}", re.S)
DOUBLES_OF = {"MS": "MD", "WS": "WD"}  # a singles label on a two-player row
DEPTH_CODE = {0: ("F", 90), 1: ("SF", 80), 2: ("QF", 70), 3: ("R16", 40),
              4: ("R32", 30), 5: ("R64", 20), 6: ("R128", 10)}


def _players(side: str) -> list[tuple[str, str, str | None]]:
    """'{{DNK|#}} [[A (Badminton)|A]] / {{DNK|#}} [[B]]' -> [(title, display, country)]."""
    out = []
    for part in re.split(r"\s+/\s+", side):
        flag = FLAG.search(part)
        country = flag.group(1) if flag else None
        m = LINK.search(part)
        if m:
            title = m.group(1).strip()
            display = (m.group(2) or m.group(1)).strip()
        else:
            display = re.sub(r"\{\{[^}]*\}\}|'''?|<[^>]+>", "", part).strip()
            title = display
        if not display or title.lower().startswith(("datei:", "file:")):
            continue
        if is_bye(display) or is_bye(title) or "freilos" in display.lower():
            return []  # a bye is not a contest: drop the whole side

        out.append((title, display, country))
    return out


def _score(raw: str):
    """-> (games, status) or None if unparseable. Winner is listed first."""
    raw = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^/]*/>|\{\{[^}]*\}\}", "", raw).strip()
    if WALKOVER.search(raw) and not GAME.search(raw):
        return [], "Walkover"
    games = [(int(a), int(b)) for a, b in GAME.findall(raw)]
    if not games:
        return None
    status = "Retired" if RETIRED.search(raw) else "Normal"
    return games, status


def start_date(text: str, year: int | None) -> date | None:
    """'Sie fanden vom 10. bis zum 16. Juli 1995 in Jakarta statt.' -> 1995-07-10."""
    lead = re.split(r"\n==", text, 1)[0]
    for m in LEAD_DATE.finditer(lead):
        y = int(m.group(3))
        if year is None or abs(y - year) <= 1:
            try:
                return date(y, MONTHS[m.group(2).lower()], int(m.group(1)))
            except ValueError:
                continue
    return None


def _event_of(heading: str) -> str | None:
    low = heading.lower()
    for word, ev in DISCIPLINES:
        if word in low:
            return ev
    return None


def _assign_rounds(matches: list[dict]) -> None:
    """Fill round_name/round_order for one (event, stage) section, in order.

    Rounds are numbered forward: a match's round is one more than the latest
    round either side has already played (a seed with a bye joins against a
    round-1 winner, so the match is still round 2). Main-draw labels are then
    anchored on the LAST round's size — 1 match = final, 2 = semi-finals (the
    article omits the final), … — so a missing final can't shift every label.
    """
    if not matches:
        return
    # Track whole SIDES (a pair stays together within an event): following
    # single players chains unrelated matches when two people share a name.
    played: dict[frozenset, int] = {}
    rounds = []
    for m in matches:
        sides = [frozenset(p[0] for p in m["side1"]), frozenset(p[0] for p in m["side2"])]
        r = 1 + max(played.get(sd, 0) for sd in sides)
        for sd in sides:
            played[sd] = r
        rounds.append(r)
    if matches[0]["stage"] == "qual":
        for m, r in zip(matches, rounds):
            m["round_name"], m["round_order"] = f"Q{r}", min(r, 9)
        return
    last = max(rounds)
    in_last = rounds.count(last)
    offset = max(0, round(math.log2(in_last))) if in_last else 0
    for m, r in zip(matches, rounds):
        depth = (last - r) + offset  # 0 = final
        m["round_name"], m["round_order"] = DEPTH_CODE.get(depth, ("R", 5))


def _bracket_matches(text: str, pos: int, size: int, event: str) -> tuple[list[dict], int]:
    """Matches in the Turnierplan template at `pos` (in round order) and the
    offset just past it."""
    body = _template_body(text, pos)
    out = []
    for m in sorted(_parse_one(body, size, event), key=lambda x: x["round_index"]):
        def side(d):
            return [(t, disp, d.get("country")) for t, disp in d["players"]]
        out.append({
            "event": event, "side1": side(m["side1"]), "side2": side(m["side2"]),
            "games": m["games"], "winner_side": m["winner_side"],
            "status": "Retired" if m.get("retired") else "Normal",
        })
    return out, pos + len(body)



def _cell(raw: str) -> str:
    """'rowspan="2"| text' -> 'text' (a lone '|' splits attributes from content)."""
    raw = raw.strip()
    if "|" in raw and "[[" not in raw.split("|", 1)[0] and "{{" not in raw.split("|", 1)[0]:
        raw = raw.split("|", 1)[1]
    return raw.strip()


def finals_table(text: str) -> list[dict]:
    """Finals from a 'Finalergebnisse' table (Disziplin | Sieger | Finalist |
    Ergebnis): the only results many 1980s/90s articles carry."""
    out = []
    for tm in TABLE.finditer(text):
        body = tm.group(1)
        head = body.lower()
        if not ("sieger" in head and "finalist" in head and "ergebnis" in head):
            continue
        for row in re.split(r"\n\|-[^\n]*", body)[1:]:
            cells = [_cell(c) for c in re.split(r"\n\|\s?|\|\|", "\n" + row.strip())
                     if c.strip()]
            if len(cells) < 4:
                continue
            event = _event_of(cells[0])
            if not event:
                continue
            s1 = _players(re.sub(r"<br\s*/?>", " / ", cells[1]))
            s2 = _players(re.sub(r"<br\s*/?>", " / ", cells[2]))
            sc = _score(cells[3])
            if not s1 or not s2 or sc is None or len(s1) != len(s2) or len(s1) > 2:
                continue
            if len(s1) == 2:
                event = DOUBLES_OF.get(event, event)
            elif event in ("MD", "WD", "XD"):
                continue
            games, status = sc
            if "aufgabe" in cells[3].lower():
                status = "Retired"
            out.append({"event": event, "stage": "main", "side1": s1, "side2": s2,
                        "games": games, "winner_side": 1, "status": status,
                        "round_name": "F", "round_order": 90})
    return out


def parse_article(text: str) -> list[dict]:
    """All matches in a German tournament article.

    Each: {event, stage ('main'|'qual'), round_name, round_order, side1/side2:
    [(de_title, display, country)], games [(s1, s2)], winner_side, status}.
    """
    event = None
    stage = "main"
    sections: dict[tuple[str, str], list[dict]] = {}
    pos = 0
    skip_to = 0
    for line in text.splitlines(keepends=True):
        start, pos = pos, pos + len(line)
        if start < skip_to:
            continue
        line = line.rstrip("\n")
        h = HEADING.match(line)
        if h:
            level, name = len(h.group(1)), h.group(2)
            ev = _event_of(name)
            if ev:
                event, stage = ev, ("qual" if QUAL.search(name) else "main")
            elif QUAL.search(name):
                stage = "qual"
            elif level <= 2:
                event = None  # 'Sieger', 'Weblinks', … end the discipline
            elif re.search(r"hauptrunde|hauptfeld|endrunde|runde|finale|sektion", name, re.I):
                stage = "main"
            # other level-3+ headings ('Setzliste') keep the discipline
            continue
        if event is None:
            continue
        tp = TURNIERPLAN.search(line)
        if tp:
            found, skip_to = _bracket_matches(text, start + tp.start(), int(tp.group(1)), event)
            for m in found:
                m["stage"] = stage
            sections.setdefault((event, stage), []).extend(found)
            continue
        m = LINE.match(line)
        if not m:
            continue
        s1, s2 = _players(m.group("s1")), _players(m.group("s2"))
        sc = _score(m.group("score"))
        if not s1 or not s2 or sc is None or len(s1) > 2 or len(s2) > 2:
            continue
        games, status = sc
        sections.setdefault((event, stage), []).append({
            "event": event, "stage": stage, "side1": s1, "side2": s2,
            "games": games, "winner_side": 1, "status": status,
        })
    out = []
    for ms in sections.values():
        _assign_rounds(ms)
        out += ms
    # A finals table only fills disciplines the article has no match list for.
    have = {m["event"] for m in out}
    seen = set()
    for f in finals_table(text):
        if f["event"] not in have and f["event"] not in seen:
            seen.add(f["event"])
            out.append(f)
    return out
