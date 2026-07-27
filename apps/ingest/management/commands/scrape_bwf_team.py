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

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import RawCache, Tournament
from apps.ingest.normalize import (
    normalize_team_rubber,
    synthetic_tournament_id,
)
from apps.ingest.schemas import MatchRaw

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


class Command(BaseCommand):
    help = "Ingest BWF team championships (tmtIds) as gendered tournaments."

    def add_arguments(self, p):
        p.add_argument("tmt_ids", nargs="+", type=int, help="BWF numeric tmtId(s)")
        p.add_argument("--refresh", action="store_true", help="ignore cache")

    def handle(self, *a, **o):
        with BwfClient() as client:
            for tmt in o["tmt_ids"]:
                try:
                    self._one(client, tmt, o["refresh"])
                except Exception as e:  # keep going across tournaments
                    self.stdout.write(self.style.ERROR(f"  ! tmt {tmt}: {e}"))

    def _one(self, client, tmt, refresh):
        if refresh:
            RawCache.objects.filter(pk__in=[
                endpoints.vue_tournament_detail(tmt),
                endpoints.vue_tournament_draws(tmt)]).delete()
        det = _res(client.get_json(endpoints.vue_tournament_detail(tmt)))
        draws = _res(client.get_json(endpoints.vue_tournament_draws(tmt)))
        name = det.get("name") or f"Tournament {tmt}"
        tier = (det.get("categoryModel") or {}).get("name") or "Continental Team Championships"
        start, end = _to_date(det.get("start_date")), _to_date(det.get("end_date"))
        logo = det.get("tmtLogo") or ""
        guid = det.get("code") or str(tmt)
        self.stdout.write(f"[{tmt}] {name}  ({len(draws)} draws)")

        by_gender: dict[str, list] = {"M": [], "W": []}
        for dw in draws:
            g = "W" if "women" in (dw.get("text") or "").lower() else "M"
            by_gender[g].append(dw)

        for gender, dws in by_gender.items():
            if not dws:
                continue
            suffix = "Men's team" if gender == "M" else "Women's team"
            total, failed = self._ingest_gender(
                client, tmt, guid, gender, suffix, name, tier, start, end, logo, dws, refresh)
            note = f"  (missing draws: {', '.join(failed)})" if failed else ""
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {name} – {suffix}: {total} rubbers{note}"))

    @transaction.atomic
    def _ingest_gender(self, client, tmt, guid, gender, suffix, name, tier,
                       start, end, logo, dws, refresh):
        code = f"{guid}:{gender}"
        t, _ = Tournament.objects.update_or_create(
            tournament_id=synthetic_tournament_id(code),
            defaults={
                "code": code,
                "name": f"{name} – {suffix}",
                "category_name": tier,
                "start_date": start,
                "end_date": end,
                "logo_url": logo,
            },
        )
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
            for tie in dd.get("matches") or []:
                rname, rorder = team_round(dw.get("text"), tie.get("roundName"))
                c1 = (tie.get("team1") or {}).get("countryCode") or ""
                c2 = (tie.get("team2") or {}).get("countryCode") or ""
                for rub in tie.get("matches") or []:
                    try:
                        raw = MatchRaw.model_validate(rub)
                    except Exception:
                        continue
                    if not raw.team1 or not raw.team2:
                        continue
                    normalize_team_rubber(
                        raw, tournament=t, gender=gender,
                        round_name=rname, round_order_=rorder,
                        side1_country=c1, side2_country=c2,
                        match_date_fallback=start,
                    )
                    total += 1
        return total, failed


def _res(payload):
    r = payload.get("results", payload) if isinstance(payload, dict) else payload
    return r
