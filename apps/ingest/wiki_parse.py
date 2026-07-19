"""Parse Wikipedia badminton bracket templates into plain match records.

Pure module — no Django, no network. Input is the wikitext of a section that
contains one or more `{{NNTeamBracket-...}}` templates (the standard tennis
bracket family Wikipedia uses for badminton draws). Output is a list of
`WikiMatch` dicts the ingest layer turns into Match/Game/MatchPlayer rows.

Bracket grammar (see [[wikipedia-gap-source]] memory):
    | RD{r}=<round label>
    | RD{r}-team{NN}={{flagicon|CC}} [[Player]]  (doubles: two [[links]])
    | RD{r}-score{NN}-{g}=<points>
Teams pair up per round: slots (1,2),(3,4),… play each other. The player who
wins more games — or, on ties/blanks, whoever appears in the next round — is the
winner. The `[[wiki title]]` is the player's stable identity.
"""
from __future__ import annotations

import re

FLAG_RE = re.compile(r"\{\{\s*(?:flagicon|flagathlete|fb|fbw|flag)\s*\|\s*([^}|]+)", re.I)

# Full country names (as used in {{flagicon|China}}) -> IOC-ish code. 2-3 letter
# flag args are used as-is; anything longer is looked up here.
COUNTRY_CODE = {
    "china": "CHN", "indonesia": "INA", "denmark": "DEN", "south korea": "KOR",
    "korea": "KOR", "malaysia": "MAS", "japan": "JPN", "england": "ENG",
    "india": "IND", "thailand": "THA", "chinese taipei": "TPE", "taiwan": "TPE",
    "hong kong": "HKG", "singapore": "SGP", "netherlands": "NED", "germany": "GER",
    "france": "FRA", "sweden": "SWE", "united states": "USA", "canada": "CAN",
    "spain": "ESP", "russia": "RUS", "poland": "POL", "scotland": "SCO",
    "wales": "WAL", "ireland": "IRL", "finland": "FIN", "norway": "NOR",
    "bulgaria": "BUL", "ukraine": "UKR", "vietnam": "VIE", "australia": "AUS",
    "new zealand": "NZL", "czech republic": "CZE", "switzerland": "SUI",
    "austria": "AUT", "italy": "ITA", "belgium": "BEL", "portugal": "POR",
    "brazil": "BRA", "mexico": "MEX", "hungary": "HUN", "estonia": "EST",
    "sri lanka": "SRI", "myanmar": "MYA", "peru": "PER",
}


def _country(raw: str) -> str | None:
    raw = raw.strip()
    if 2 <= len(raw) <= 3 and raw.isalpha():
        return raw.upper()
    return COUNTRY_CODE.get(raw.lower())
LINK_RE = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|\s*([^\]]+?)\s*)?\]\]")
PARAM_RE = re.compile(r"^\s*\|\s*(RD\d+(?:-team\d+|-score\d+-\d+)?)\s*=\s*(.*?)\s*$", re.M)
BRACKET_RE = re.compile(r"\{\{\s*(\d+)TeamBracket[^\n}|]*", re.I)
SEED_RE = re.compile(r"\(\s*(\d+)\s*\)")
RETIRE_RE = re.compile(r"\b(ret\.?|retired|w/?o|walkover|def\.?|conceded)\b", re.I)


def _clean(raw: str) -> str:
    # strip wiki bold/italic ('''name''') and tags (<br/>) that pollute names
    raw = re.sub(r"'{2,}|<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def parse_team(raw: str) -> dict | None:
    """One team slot -> {country, players:[(title,display)], seed}. None if empty."""
    raw = raw.strip()
    if not raw or raw in {"-", "—", "bye", "Bye", "BYE"}:
        return None
    country = None
    m = FLAG_RE.search(raw)
    if m:
        country = _country(m.group(1))
    players = []
    for lm in LINK_RE.finditer(raw):
        title = _clean(lm.group(1))
        disp = _clean(lm.group(2) or lm.group(1))
        # skip file/category links
        if title.lower().startswith(("file:", "image:", "category:")):
            continue
        players.append((title, disp))
    if not players:
        txt = re.sub(r"\{\{[^}]*\}\}", "", raw)          # drop templates (flag)
        txt = re.sub(r"\(\s*\d+\s*\)", "", txt)          # drop seed
        txt = _clean(txt)
        if not txt or txt.lower() in {"bye", "tbd"}:
            return None
        players.append((txt, txt))
    seed = None
    sm = SEED_RE.search(raw)
    if sm:
        seed = sm.group(1)
    return {"country": country, "players": players, "seed": seed}


def _score_int(v: str):
    # strip wiki bold/italic ('''15'''), tags (<sup>), and templates first
    v = re.sub(r"'{2,}|<[^>]+>|\{\{[^}]*\}\}", "", v).strip()
    m = re.search(r"\d+", v)
    return int(m.group()) if m else None


EVENT_FROM_CATEGORY = {
    "men's singles": "MS", "women's singles": "WS", "men's doubles": "MD",
    "women's doubles": "WD", "mixed doubles": "XD",
}


def parse_score_string(s: str):
    """'15–4, 15–1' or '21-19, 18-21, 21-17' -> [(15,4),(15,1)], retired?"""
    retired = bool(RETIRE_RE.search(s))
    games = []
    for part in re.split(r"[,;]", s):
        part = part.strip()
        m = re.match(r"(\d+)\s*[-–—]\s*(\d+)", part)
        if m:
            games.append((int(m.group(1)), int(m.group(2))))
    return games, retired


def parse_final_table(text: str) -> list[dict]:
    """Parse the 'Final results' wikitable -> one Final match per discipline.

    Rows are: Category | Winners | Runners-up | Score. This is the only place
    the tournament final itself appears (section brackets stop at the SF)."""
    out = []
    # split into table cells across rows: each data row starts with |-
    for row in re.split(r"\n\|-", text):
        cells = re.split(r"\n\s*\|", row)
        cells = [c.strip() for c in cells if c.strip() and not c.strip().startswith("!")]
        if len(cells) < 4:
            continue
        cat = _clean(re.sub(r"[|]", "", cells[0])).lower()
        event = EVENT_FROM_CATEGORY.get(cat)
        if not event:
            continue
        winner = parse_team(cells[1])
        runner = parse_team(cells[2])
        if not winner or not runner:
            continue
        games, retired = parse_score_string(cells[3])
        out.append({
            "event": event,
            "round_label": "Final",
            "round_index": 99,
            "bracket_size": 2,
            "side1": winner,
            "side2": runner,
            "games": games,
            "winner_side": 1,
            "retired": retired,
        })
    return out


def _template_body(text: str, start: int) -> str:
    """Slice the `{{...}}` template beginning at `start`, matching nested braces
    so we don't bleed a following bracket's params into this one."""
    depth, i, n = 0, start, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "{{":
            depth += 1; i += 2
        elif two == "}}":
            depth -= 1; i += 2
            if depth == 0:
                return text[start:i]
        else:
            i += 1
    return text[start:]


def parse_bracket(text: str, event: str) -> list[dict]:
    """All matches from every bracket template in `text`, deduped within it."""
    matches: list[dict] = []
    for bm in BRACKET_RE.finditer(text):
        size = int(bm.group(1))
        body = _template_body(text, bm.start())
        matches.extend(_parse_one(body, size, event))
    return _dedupe(matches)


def _parse_one(body: str, size: int, event: str) -> list[dict]:
    teams: dict[tuple[int, int], str] = {}
    scores: dict[tuple[int, int, int], str] = {}
    rounds: dict[int, str] = {}
    for pm in PARAM_RE.finditer(body):
        key, val = pm.group(1), pm.group(2)
        t = re.match(r"RD(\d+)-team(\d+)$", key)
        s = re.match(r"RD(\d+)-score(\d+)-(\d+)$", key)
        r = re.match(r"RD(\d+)$", key)
        if t:
            teams[(int(t.group(1)), int(t.group(2)))] = val
        elif s:
            scores[(int(s.group(1)), int(s.group(2)), int(s.group(3)))] = val
        elif r:
            rounds[int(r.group(1))] = _clean(val)
    if not teams:
        return []
    max_rd = max(r for r, _ in teams)
    out = []
    for rd in range(1, max_rd + 1):
        slots = sorted(nn for (r, nn) in teams if r == rd)
        # pair consecutive slots (1,2),(3,4)...
        for i in range(0, len(slots) - 1, 2):
            a, b = slots[i], slots[i + 1]
            ta = parse_team(teams.get((rd, a), ""))
            tb = parse_team(teams.get((rd, b), ""))
            if not ta or not tb:
                continue
            games = []
            retired = False
            for g in range(1, 6):
                va = scores.get((rd, a, g))
                vb = scores.get((rd, b, g))
                if va is None and vb is None:
                    continue
                if (va and RETIRE_RE.search(va)) or (vb and RETIRE_RE.search(vb)):
                    retired = True
                pa, pb = _score_int(va or ""), _score_int(vb or "")
                if pa is None and pb is None:
                    continue
                games.append((pa or 0, pb or 0))
            games = _trim_clinched(games)
            winner = _winner(ta, tb, games, teams, rounds, rd, a, b)
            if winner is None:
                continue
            out.append({
                "event": event,
                "round_label": rounds.get(rd, f"RD{rd}"),
                "round_index": rd,
                "bracket_size": size,
                "side1": ta,
                "side2": tb,
                "games": games,
                "winner_side": winner,
                "retired": retired,
            })
    return out


def _advances(team: dict, teams: dict, rd: int) -> bool:
    """Does this team's first player title appear anywhere in round rd+1?"""
    if not team or not team["players"]:
        return False
    title = team["players"][0][0].lower()
    for (r, _), raw in teams.items():
        if r == rd + 1 and title in raw.lower():
            return True
    return False


def _trim_clinched(games):
    """Drop games after a side has clinched a best-of-3 (2 games won). Strips
    the spurious trailing '(3,0)'-style cells some brackets leave behind."""
    w1 = w2 = 0
    out = []
    for pa, pb in games:
        out.append((pa, pb))
        if pa > pb:
            w1 += 1
        elif pb > pa:
            w2 += 1
        if w1 == 2 or w2 == 2:
            break
    return out


def _winner(ta, tb, games, teams, rounds, rd, a, b):
    """1 if side1 won, 2 if side2, None if undecidable (skip)."""
    wa = sum(1 for pa, pb in games if pa > pb)
    wb = sum(1 for pa, pb in games if pb > pa)
    if games and wa != wb:
        return 1 if wa > wb else 2
    # tie/blank -> use advancement
    adv_a, adv_b = _advances(ta, teams, rd), _advances(tb, teams, rd)
    if adv_a and not adv_b:
        return 1
    if adv_b and not adv_a:
        return 2
    return None  # can't tell (e.g. the tournament final, or unplayed)


def _split_params(template: str) -> list[str]:
    """Split a `{{...}}` template body into top-level |-separated parts,
    respecting nested {{ }}, [[ ]] so inner templates/links stay intact.
    parts[0] is the template name; the rest are its params/positional args."""
    s = template.strip()
    if s.startswith("{{"):
        s = s[2:]
    if s.endswith("}}"):
        s = s[:-2]
    parts, buf, depth, i, n = [], [], 0, 0, len(s)
    while i < n:
        two = s[i:i + 2]
        if two in ("{{", "[["):
            depth += 1; buf.append(two); i += 2
        elif two in ("}}", "]]"):
            depth -= 1; buf.append(two); i += 2
        elif s[i] == "|" and depth == 0:
            parts.append("".join(buf)); buf = []; i += 1
        else:
            buf.append(s[i]); i += 1
    parts.append("".join(buf))
    return parts


def _players_from(raw: str) -> list[tuple[str, str]]:
    out = []
    for lm in LINK_RE.finditer(raw):
        title = _clean(lm.group(1))
        if title.lower().startswith(("file:", "image:", "category:")):
            continue
        out.append((title, _clean(lm.group(2) or lm.group(1))))
    return out


def parse_badminton_match(rv: str):
    """One {{BadmintonMatch}} rubber -> (team1 players, team2 players, games) or
    None if not played (np=). Params: T1P1/T1P2 then team1 game scores, then
    T2P1/T2P2 then team2 game scores (scores are positional)."""
    parts = _split_params(rv)[1:]
    t1, t2, s1, s2, side, played = [], [], [], [], 1, True
    for p in parts:
        km = re.match(r"\s*([A-Za-z0-9]+)\s*=(.*)$", p, re.S)
        if km:
            k, v = km.group(1).lower(), km.group(2).strip()
            if k == "np":
                played = False
            elif k.startswith("t1p"):
                t1 += _players_from(v); side = 1
            elif k.startswith("t2p"):
                t2 += _players_from(v); side = 2
            # ignore other named params
        else:
            (s1 if side == 1 else s2).append(p.strip())
    if not played or not t1 or not t2:
        return None
    games = []
    for a, b in zip(s1, s2):
        ia, ib = _score_int(a), _score_int(b)
        if ia is None and ib is None:
            continue
        games.append((ia or 0, ib or 0))
    return t1, t2, _trim_clinched(games)


CUP_EVENT = {
    "thomas": lambda d, r: "MD" if d else "MS",
    "uber": lambda d, r: "WD" if d else "WS",
    "sudirman": lambda d, r: {1: "MS", 2: "WS", 3: "MD", 4: "WD", 5: "XD"}.get(
        r, "XD" if d else "MS"),
}


def parse_team_ties(text: str, cup: str) -> list[dict]:
    """All individual rubbers from a team-cup article's {{Badmintonbox}} ties.
    `cup` in {thomas, uber, sudirman} sets how rubber -> discipline."""
    ev_fn = CUP_EVENT.get(cup, CUP_EVENT["thomas"])
    # The STAGE is the level-2 header (== Group A ==, == Quarter-finals ==);
    # level-3 headers are individual ties (=== China vs Denmark ===). Track only
    # level-2 so a rubber's round is its stage, not the opponent-nation heading.
    heads = [(m.start(), _clean(m.group(2)))
             for m in re.finditer(r"^(=+)\s*(.+?)\s*=+\s*$", text, re.M)
             if len(m.group(1)) == 2]
    out = []
    for bm in re.finditer(r"\{\{\s*Badmintonbox\b", text, re.I):
        body = _template_body(text, bm.start())
        parts = _split_params(body)
        team1 = team2 = ""
        rubbers = []
        for p in parts[1:]:
            km = re.match(r"\s*([A-Za-z0-9]+)\s*=(.*)$", p, re.S)
            if not km:
                continue
            k, v = km.group(1).lower(), km.group(2)
            if k == "team1":
                team1 = _clean(v)
            elif k == "team2":
                team2 = _clean(v)
            elif re.match(r"r\d+$", k):
                rubbers.append((int(k[1:]), v))
        c1, c2 = _country(team1) or None, _country(team2) or None
        # round = nearest preceding level-2 header (the stage)
        rnd = "Group stage"
        for start, name in heads:
            if start <= bm.start():
                rnd = name
            else:
                break
        for ridx, rv in rubbers:
            if "BadmintonMatch" not in rv:
                continue
            parsed = parse_badminton_match(rv)
            if parsed is None:
                continue
            p1, p2, games = parsed
            doubles = len(p1) == 2 or len(p2) == 2
            out.append({
                "event": ev_fn(doubles, ridx),
                "round_label": rnd,
                "round_index": 50,  # ties are ordered by tournament date + section
                "bracket_size": 2,
                "side1": {"country": c1, "players": p1, "seed": None},
                "side2": {"country": c2, "players": p2, "seed": None},
                "games": games,
                "winner_side": _team_winner(games),
                "retired": False,
            })
    return _dedupe(out)


def _team_winner(games):
    wa = sum(1 for a, b in games if a > b)
    wb = sum(1 for a, b in games if b > a)
    if not games or wa == wb:
        return None
    return 1 if wa > wb else 2


DISCIPLINE_HEADERS = [
    ("mixed doubles", "XD"), ("men's doubles", "MD"), ("women's doubles", "WD"),
    ("men's singles", "MS"), ("women's singles", "WS"),
]
HEADER_RE = re.compile(r"^==+\s*(.+?)\s*==+\s*$", re.M)


def parse_article(text: str) -> list[dict]:
    """All matches from a full tournament article: the finals table + every
    discipline bracket (event inferred from the enclosing section header)."""
    matches = parse_final_table(text)
    heads = list(HEADER_RE.finditer(text))
    current = None
    for i, h in enumerate(heads):
        name = h.group(1).lower()
        # word-boundary match: "women's singles" must NOT match "men's singles"
        ev = next((code for key, code in DISCIPLINE_HEADERS
                   if re.search(r"\b" + re.escape(key) + r"\b", name)), None)
        if ev:
            current = ev
        if current:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            matches.extend(parse_bracket(text[h.start():end], current))
    return _dedupe(matches)


def _key(m):
    def names(t):
        return tuple(sorted(p[0].lower() for p in t["players"]))
    return (m["event"], frozenset([names(m["side1"]), names(m["side2"])]),
            tuple(m["games"]))


def _dedupe(matches):
    seen, out = set(), []
    for m in matches:
        k = _key(m)
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out


dedupe = _dedupe  # public alias for combining matches across articles
