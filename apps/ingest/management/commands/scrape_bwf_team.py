"""Ingest a BWF team championship (Thomas/Uber/Sudirman/continental team events)
directly from the fan API, straight from real player ids — no Wikipedia synthetic
players or reconciliation.

BWF models a team event as one tournament with several team draws (per gender,
often split further into per-group + knock-out draws). Each draw-data entry is a
nation-vs-nation TIE (`isTeamMatch`) whose individual rubbers are nested in
`matches[]`, each with real players, scores, winner, and timestamps. We split the
event into a men's and a women's tournament (so nation ties never mix genders in
the ties view), inferring each rubber's discipline from side size + gender.

    python manage.py scrape_bwf_team 5638            # Oceania 2026 (tmtId)
    python manage.py scrape_bwf_team 5638 5661 --refresh
"""
from __future__ import annotations

import re
from datetime import date as _date

from django.core.management.base import BaseCommand
from django.db import transaction

from collections import defaultdict

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import Match, RawCache, Tournament
from apps.ingest.normalize import (
    canonical_event,
    normalize_team_rubber,
    synthetic_tournament_id,
)
from apps.ingest.schemas import GroupedYearTournaments, MatchRaw

# Calendar-name filters for the bulk (--calendar) enumeration.
_TEAM_NAME_RE = re.compile(r"\bteam\b|thomas|uber|sudirman|m&f cup|pan american cup", re.I)
_JUNIOR_RE = re.compile(r"junior|youth|\bu1[3-9]\b", re.I)

# Knock-out round label -> (display code, chronological order). Groups all sort
# before the knock-out; a pure round-robin keeps its R1..Rn rounds.
_KO = {
    "final": ("F", 90), "f": ("F", 90),
    "semi-finals": ("SF", 80), "semifinals": ("SF", 80), "sf": ("SF", 80),
    "quarter-finals": ("QF", 70), "quarterfinals": ("QF", 70), "qf": ("QF", 70),
    "r16": ("R16", 60), "round of 16": ("R16", 60),
}


def team_round(draw_text: str, tie_round: str | None) -> tuple[str, int]:
    """(round_name, round_order) for a tie, from its draw's stage + tie round.

    Group draws ('… - Group A') collapse every round-robin round into one 'Group
    A' bucket (order 10, sorted by name), so a group reads as a single stage.
    Knock-out ties use their round (QF/SF/F). A single round-robin draw with no
    group label (Oceania) keeps its R1..Rn rounds.
    """
    low = (draw_text or "").lower()
    gm = re.search(r"group\s+([a-z0-9]+)", low)
    if gm:
        return (f"Group {gm.group(1).upper()}", 10)
    # Placement/classification bracket: the draw suffix is a placing like '5/6',
    # '7/9', '9-12'. These ties are also labelled 'Final' inside their sub-bracket,
    # so give them their own round (after the main final) — otherwise the gold
    # final stops being the single 'F' tie and the champion can't be identified.
    pm = re.search(r"(\d+)\s*[/\-]\s*(\d+)\s*$", (draw_text or "").strip())
    if pm:
        return (f"{pm.group(1)}–{pm.group(2)} place", 95)
    tr = (tie_round or "").strip()
    hit = _KO.get(tr.lower())
    if hit:
        return hit
    rm = re.search(r"(\d+)", tr)
    if tr.upper().startswith("R") and rm:
        return (tr.upper(), 10 + int(rm.group(1)))
    return (tr or "RR", 15)


def _to_date(v):
    if not v:
        return None
    s = str(v).replace("T", " ").split(" ")[0]
    return _date.fromisoformat(s)


def _gendered_name(base: str, gender: str) -> str:
    """A clear per-gender tournament name. When the event name embeds BOTH genders
    ('… Men's and Women's Team Championships', 'Pan Am M&F Cup'), collapse that
    phrase to just this gender so the name reads distinctly (and the gender isn't
    hidden past a truncated card). Otherwise append a '– Men's/Women's team' tag."""
    g_full = "Men's" if gender == "M" else "Women's"
    # flexible whitespace: BWF sends e.g. "Men's  and Women's" (double space)
    combo = (r"Men'?s\s*(?:and|&|/)\s*Women'?s|\bM\s*&\s*F\b"
             r"|Men\s+and\s+Women|Male\s+(?:and|&)\s+Female")
    if re.search(combo, base, flags=re.I):
        return re.sub(r"\s{2,}", " ", re.sub(combo, g_full, base, flags=re.I)).strip()
    return f"{base} – {g_full} team"


def _gender_of(text: str) -> str:
    """'W' for a women's/female/ladies event, else 'M'. Read only the label PREFIX
    (before ' - '), because a knockout draw's suffix can carry the full event name
    — 'Men's Team - All Africa Men's & Women's Team Championships' is a MEN's draw
    despite containing 'Women's'. Check women-side words first: 'female' contains
    'male' and 'women' contains 'men' (Pan Am uses 'Male Cup' / 'Female Cup')."""
    low = (text or "").split(" - ")[0].lower()
    return "W" if ("women" in low or "female" in low or "ladies" in low) else "M"


class Command(BaseCommand):
    help = "Ingest BWF team championships (tmtIds) as gendered tournaments."

    def add_arguments(self, p):
        p.add_argument("tmt_ids", nargs="*", type=int,
                       help="BWF numeric tmtId(s); omit when using --calendar")
        p.add_argument("--refresh", action="store_true", help="ignore cache")
        p.add_argument("--day-matches", dest="day_matches", action="store_true",
                       help="collect ties via the day-matches endpoint (date by "
                            "date) instead of per-draw draw-data — use when a "
                            "draw-data draw returns a server error")
        p.add_argument("--mixed", action="store_true",
                       help="a MIXED team event (Sudirman-style: one team plays "
                            "all 5 disciplines). Ingested as ONE tournament, with "
                            "each rubber's discipline from its matchTypeValue. "
                            "Implies a day-matches sweep.")
        p.add_argument("--auto", action="store_true",
                       help="auto-detect mixed vs gendered per tmtId (mixed if any "
                            "rubber is a Mixed Doubles) and ingest accordingly")
        p.add_argument("--calendar", help="year range 'START-END': enumerate every "
                       "senior team event in the BWF calendar and ingest them all "
                       "(implies --auto)")
        p.add_argument("--skip-collected", dest="skip_collected", action="store_true",
                       help="skip events that already have matches (resumable bulk)")
        p.add_argument("--include-junior", dest="include_junior", action="store_true",
                       help="also include junior team events in --calendar")

    def handle(self, *a, **o):
        tmt_ids = o["tmt_ids"]
        with BwfClient() as client:
            if o["calendar"]:
                y0, y1 = (int(x) for x in o["calendar"].split("-"))
                tmt_ids = self._enumerate_team_events(client, y0, y1, o["include_junior"])
                self.stdout.write(f"[calendar {y0}-{y1}] {len(tmt_ids)} senior team events")
                o = {**o, "auto": True}
            for tmt in tmt_ids:
                try:
                    if o["auto"]:
                        self._detect_and_ingest(client, tmt, o["refresh"], o["skip_collected"])
                    elif o["mixed"]:
                        self._one_mixed(client, tmt, o["refresh"])
                    elif o["day_matches"]:
                        self._one_day_matches(client, tmt, o["refresh"])
                    else:
                        self._one(client, tmt, o["refresh"])
                except Exception as e:  # keep going across tournaments
                    self.stdout.write(self.style.ERROR(f"  ! tmt {tmt}: {e}"))

    # --- shared -------------------------------------------------------------
    def _meta(self, client, tmt, refresh):
        if refresh:
            RawCache.objects.filter(pk=endpoints.vue_tournament_detail(tmt)).delete()
        det = _res(client.get_json(endpoints.vue_tournament_detail(tmt)))
        return {
            "name": det.get("name") or f"Tournament {tmt}",
            "tier": (det.get("categoryModel") or {}).get("name") or "Continental Team Championships",
            "start": _to_date(det.get("start_date")),
            "end": _to_date(det.get("end_date")),
            "logo": det.get("tmtLogo") or "",
            "guid": det.get("code") or str(tmt),
        }

    def _gendered_tournament(self, meta, gender):
        code = f"{meta['guid']}:{gender}"
        t, _ = Tournament.objects.update_or_create(
            tournament_id=synthetic_tournament_id(code),
            defaults={
                "code": code,
                "name": _gendered_name(meta["name"], gender),
                "category_name": meta["tier"],
                "start_date": meta["start"],
                "end_date": meta["end"],
                "logo_url": meta["logo"],
            },
        )
        return t

    def _ingest_ties(self, t, ties, fallback_date, *, gender=None, mixed=False):
        """Ingest every rubber of a list of tie dicts. Each tie's own drawName
        gives its stage/round; rubbers are nested in tie['matches']. For a MIXED
        team event the rubber's discipline comes from matchTypeValue ('Men's
        Singles'…'Mixed Doubles'); otherwise it's inferred from side size +
        gender (a single-gender men's or women's team draw)."""
        total = 0
        for tie in ties:
            rname, rorder = team_round(tie.get("drawName"), tie.get("roundName"))
            c1 = (tie.get("team1") or {}).get("countryCode") or ""
            c2 = (tie.get("team2") or {}).get("countryCode") or ""
            for rub in tie.get("matches") or []:
                try:
                    raw = MatchRaw.model_validate(rub)
                except Exception:
                    continue
                # Skip bracket placeholders — BWF pads a tie with empty rubber
                # slots (no players) for unplayed/dead rubbers and for TBD ties in
                # placement brackets. A real rubber has a player on each side.
                if not raw.team1 or not raw.team2 \
                        or not raw.team1.players or not raw.team2.players:
                    continue
                event_override = None
                if mixed:
                    event_override = canonical_event(rub.get("matchTypeValue") or "")[0]
                    if event_override not in ("MS", "WS", "MD", "WD", "XD"):
                        continue  # can't classify this rubber's discipline
                normalize_team_rubber(
                    raw, tournament=t, gender=gender, event_override=event_override,
                    round_name=rname, round_order_=rorder,
                    side1_country=c1, side2_country=c2,
                    match_date_fallback=fallback_date,
                )
                total += 1
        return total

    # --- draw-data path (default) ------------------------------------------
    def _one(self, client, tmt, refresh):
        meta = self._meta(client, tmt, refresh)
        if refresh:
            RawCache.objects.filter(pk=endpoints.vue_tournament_draws(tmt)).delete()
        draws = _res(client.get_json(endpoints.vue_tournament_draws(tmt)))
        self.stdout.write(f"[{tmt}] {meta['name']}  ({len(draws)} draws)")
        by_gender: dict[str, list] = {"M": [], "W": []}
        for dw in draws:
            by_gender[_gender_of(dw.get("text"))].append(dw)

        for gender, dws in by_gender.items():
            if not dws:
                continue
            t = self._gendered_tournament(meta, gender)
            total = 0
            failed: list[str] = []
            for dw in dws:
                url = endpoints.vue_tournament_draw_data(tmt, dw["value"])
                if refresh:
                    RawCache.objects.filter(pk=url).delete()
                try:
                    dd = client.get_json(url)
                except Exception:
                    failed.append(dw.get("text") or str(dw.get("value")))
                    continue
                total += self._ingest_ties(t, dd.get("matches") or [], meta["start"], gender=gender)
            note = (f"  (missing draws: {', '.join(failed)} — retry with "
                    f"--day-matches)") if failed else ""
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {t.name}: {total} rubbers{note}"))

    # --- day-matches collection (robust to broken draw-data) ---------------
    def _collect_day_ties(self, client, meta, refresh):
        """Every team tie across the tournament's date range, deduped by id."""
        if not meta["start"] or not meta["end"]:
            raise RuntimeError("no start/end date for day-matches sweep")
        ties: list = []
        seen: set[int] = set()
        for day in _daterange(meta["start"], meta["end"]):
            url = endpoints.day_matches(meta["guid"], day)
            if refresh:
                RawCache.objects.filter(pk=url).delete()
            try:
                data = client.get_json(url)
            except Exception:
                continue
            for m in (data if isinstance(data, list) else _res(data) or []):
                if m.get("isTeamMatch") and m.get("id") not in seen:
                    seen.add(m.get("id"))
                    ties.append(m)
        return ties

    def _one_day_matches(self, client, tmt, refresh):
        meta = self._meta(client, tmt, refresh)
        self.stdout.write(f"[{tmt}] {meta['name']}  (day-matches "
                          f"{meta['start']}..{meta['end']})")
        by_gender: dict[str, list] = {"M": [], "W": []}
        for m in self._collect_day_ties(client, meta, refresh):
            by_gender[_gender_of(m.get("drawName") or m.get("eventName"))].append(m)
        for gender, ties in by_gender.items():
            if not ties:
                continue
            t = self._gendered_tournament(meta, gender)
            with transaction.atomic():
                total = self._ingest_ties(t, ties, meta["start"], gender=gender)
            self.stdout.write(self.style.SUCCESS(f"  ✓ {t.name}: {total} rubbers"))

    # --- mixed team (Sudirman-style: one team, all 5 disciplines) ----------
    def _one_mixed(self, client, tmt, refresh):
        meta = self._meta(client, tmt, refresh)
        self.stdout.write(f"[{tmt}] {meta['name']}  (mixed, day-matches "
                          f"{meta['start']}..{meta['end']})")
        ties = self._collect_day_ties(client, meta, refresh)
        # Fill the real tournament row (the calendar placeholder) in place, keeping
        # its existing name/venue/logo; only create it if it's somehow absent.
        t = Tournament.objects.filter(tournament_id=tmt).first()
        if t is None:
            t = Tournament.objects.create(
                tournament_id=tmt, code=meta["guid"], name=meta["name"],
                category_name=meta["tier"], start_date=meta["start"],
                end_date=meta["end"], logo_url=meta["logo"])
        with transaction.atomic():
            total = self._ingest_ties(t, ties, meta["start"], mixed=True)
        self.stdout.write(self.style.SUCCESS(f"  ✓ {t.name}: {total} rubbers"))

    # --- bulk: enumerate the calendar + auto-detect shape ------------------
    def _enumerate_team_events(self, client, y0, y1, include_junior):
        ids: list[int] = []
        seen: set[int] = set()
        for year in range(y0, y1 + 1):
            try:
                raw = client.get_json(
                    endpoints.vue_grouped_year_tournaments(year, endpoints.ALL_CATEGORIES))
            except Exception:
                continue
            data = GroupedYearTournaments.model_validate(
                raw if isinstance(raw, dict) else {"results": raw})
            for t in data.all_tournaments():
                hay = f"{t.name} {t.category}"
                if not _TEAM_NAME_RE.search(hay):
                    continue
                if not include_junior and _JUNIOR_RE.search(hay):
                    continue
                if t.id not in seen:
                    seen.add(t.id)
                    ids.append(t.id)
        return ids

    def _detect_and_ingest(self, client, tmt, refresh, skip_collected):
        """Ingest one team event, auto-detecting its shape. A MIXED event (any
        rubber is Mixed Doubles) fills the real tournament in place; a gendered
        event splits into men's/women's tournaments and drops the empty
        placeholder so it doesn't linger as a 0-match card."""
        meta = self._meta(client, tmt, refresh)
        if not meta["start"] or not meta["end"]:
            return
        ties = self._collect_day_ties(client, meta, refresh)
        if not ties:
            return
        is_mixed = any(
            canonical_event(r.get("matchTypeValue") or "")[0] == "XD"
            for tie in ties for r in (tie.get("matches") or []))

        if is_mixed:
            t = Tournament.objects.filter(tournament_id=tmt).first()
            if skip_collected and t and t.matches.exists():
                return
            if t is None:
                t = Tournament.objects.create(
                    tournament_id=tmt, code=meta["guid"], name=meta["name"],
                    category_name=meta["tier"], start_date=meta["start"],
                    end_date=meta["end"], logo_url=meta["logo"])
            with transaction.atomic():
                n = self._ingest_ties(t, ties, meta["start"], mixed=True)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [mixed] {t.name[:48]}: {n}"))
            return

        by_gender: dict[str, list] = defaultdict(list)
        for m in ties:
            by_gender[_gender_of(m.get("drawName") or m.get("eventName"))].append(m)
        codes = [f"{meta['guid']}:{g}" for g in by_gender]
        if skip_collected and Match.objects.filter(tournament__code__in=codes).exists():
            return
        for gender, gties in by_gender.items():
            t = self._gendered_tournament(meta, gender)
            with transaction.atomic():
                n = self._ingest_ties(t, gties, meta["start"], gender=gender)
            self.stdout.write(self.style.SUCCESS(f"  ✓ [gendered] {t.name[:48]}: {n}"))
        # the split lives under synthetic ids — drop the now-empty real placeholder
        ph = Tournament.objects.filter(tournament_id=tmt).first()
        if ph is not None and not ph.matches.exists():
            ph.delete()


def _daterange(start, end):
    from datetime import timedelta
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


def _res(payload):
    r = payload.get("results", payload) if isinstance(payload, dict) else payload
    return r
