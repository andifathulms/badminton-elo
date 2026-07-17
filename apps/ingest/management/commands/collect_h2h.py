"""`manage.py collect_h2h` — enrich matches with rally stats + point progression,
and capture player bio + BWF World Ranking (for seeding).

Two BWF h2h endpoints (confirmed 2026-07-17):
  * h2h/match?tmt_id=&match_code=      -> per-match rally stats + per-point score
  * h2h/statistics?t1p1=&t1p2=&t2p1=&t2p2= -> currentRank + careerStats + bio

Cache-first and rate-limited (BwfClient). Resumable: matches that already have
a MatchStatistics row are skipped. Scope with --year / --limit / --code.

    python manage.py collect_h2h --year 2026
    python manage.py collect_h2h --year 2026 --no-stats   # only bio + ranks
    python manage.py collect_h2h --code <GUID> --limit 50
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import (
    Match,
    MatchPlayer,
    MatchStatistics,
    Player,
    PlayerSeedRank,
)

logger = logging.getLogger(__name__)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    # "2003-08-15 00:00:00" -> "2003-08-15"
    if not v:
        return None
    return str(v).split(" ")[0][:10] or None


class Command(BaseCommand):
    help = "Enrich matches with h2h rally stats, point progression, bio, ranks."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="Limit to a tournament year.")
        parser.add_argument("--code", help="Limit to one tournament GUID.")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--no-stats",
            action="store_true",
            help="Skip h2h/match; only capture bio + ranks from h2h/statistics.",
        )
        parser.add_argument("--no-cache", action="store_true")

    def handle(self, *args, **opts):
        qs = (
            Match.objects.filter(rating_excluded=False)
            .exclude(code="")
            .select_related("tournament")
            .order_by("-match_time_utc", "-match_id")
        )
        if opts["year"]:
            qs = qs.filter(tournament__start_date__year=opts["year"])
        if opts["code"]:
            qs = qs.filter(tournament__code=opts["code"])
        # Resume: skip matches already enriched.
        qs = qs.exclude(stats__isnull=False)
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        lineups = self._lineups()
        n_stats = n_h2h = n_fail = 0
        with BwfClient(use_cache=not opts["no_cache"]) as client:
            for m in qs.iterator():
                try:
                    if not opts["no_stats"]:
                        if self._collect_match_stats(client, m):
                            n_stats += 1
                    if self._collect_h2h(client, m, lineups.get(m.match_id)):
                        n_h2h += 1
                except Exception:  # noqa: BLE001 - isolate one match, keep going
                    logger.exception("h2h failed for match %s", m.match_id)
                    n_fail += 1
                if (n_stats + n_h2h) and (n_stats + n_h2h) % 200 == 0:
                    self.stdout.write(
                        f"  …{n_stats} stats, {n_h2h} h2h, {n_fail} failed"
                    )
        self.stdout.write(
            self.style.SUCCESS(
                f"done: {n_stats} match-stats, {n_h2h} h2h captured, {n_fail} failed."
            )
        )

    def _lineups(self) -> dict:
        out: dict[int, dict] = {}
        for mid, side, pid in MatchPlayer.objects.values_list(
            "match_id", "side", "player_id"
        ).iterator():
            out.setdefault(mid, {1: [], 2: []})[side].append(pid)
        return out

    # -- h2h/match: rally stats + point progression -------------------------
    def _collect_match_stats(self, client, m) -> bool:
        raw = client.get_json(endpoints.h2h_match(m.tournament_id, m.code))
        if not isinstance(raw, dict) or "stats" not in raw:
            return False
        s = raw.get("stats") or {}
        progression = [
            [[_int(d.get("team1")), _int(d.get("team2"))]
             for d in (g.get("match_set_details_model") or [])]
            for g in (raw.get("games") or [])
        ]
        MatchStatistics.objects.update_or_create(
            match=m,
            defaults={
                "team1_rallies_won": _int(s.get("team1_rallies_won")),
                "team1_rallies_played": _int(s.get("team1_rallies_played")),
                "team2_rallies_won": _int(s.get("team2_rallies_won")),
                "team2_rallies_played": _int(s.get("team2_rallies_played")),
                "team1_consecutive_points": _int(s.get("team1_consecutive_points")),
                "team2_consecutive_points": _int(s.get("team2_consecutive_points")),
                "team1_game_points": _int(s.get("team1_game_points")),
                "team2_game_points": _int(s.get("team2_game_points")),
                "duration_min": _int((raw.get("progress") or {}).get("duration")),
                "point_progression": progression or None,
                "fetched_utc": timezone.now(),
            },
        )
        return True

    # -- h2h/statistics: bio + ranks ----------------------------------------
    def _collect_h2h(self, client, m, line) -> bool:
        if not line or not line.get(1) or not line.get(2):
            return False
        s1, s2 = line[1], line[2]
        url = endpoints.h2h_statistics(
            s1[0], s1[1] if len(s1) > 1 else None,
            s2[0], s2[1] if len(s2) > 1 else None,
        )
        raw = client.get_json(url)
        if not isinstance(raw, dict):
            return False

        # Bio: players.t1p1..t2p2 map to the ids we passed, in order.
        slots = {"t1p1": s1[0], "t1p2": s1[1] if len(s1) > 1 else None,
                 "t2p1": s2[0], "t2p2": s2[1] if len(s2) > 1 else None}
        for slot, pid in slots.items():
            bio = (raw.get("players") or {}).get(slot)
            if pid and bio:
                self._fill_bio(pid, bio)

        # Ranks: ranking.team{1,2} carry the (pair or individual) BWF rank.
        match_date = m.match_time_utc.date() if m.match_time_utc else None
        for team_key, ids in (("team1", s1), ("team2", s2)):
            rank = self._bwf_rank((raw.get("ranking") or {}).get(team_key))
            if rank:
                for pid in ids:
                    self._observe_rank(pid, m.event, rank, match_date)
        return True

    def _fill_bio(self, pid, bio):
        fields = {}
        if bio.get("dob") and (d := _date(bio["dob"])):
            fields["dob"] = d
        if bio.get("height"):
            fields["height_cm"] = _int(bio["height"])
        if bio.get("plays") not in (None, ""):
            fields["plays"] = str(bio["plays"])
        if fields:
            Player.objects.filter(player_id=pid).update(**fields)

    def _bwf_rank(self, team_ranks):
        for r in team_ranks or []:
            if "world ranking" in str(r.get("rankingName", "")).lower():
                return _int(r.get("currentRank"))
        return None

    def _observe_rank(self, pid, event, rank, date):
        existing = PlayerSeedRank.objects.filter(player_id=pid, event=event).first()
        if existing is None:
            PlayerSeedRank.objects.create(
                player_id=pid, event=event, rank=rank, observed_date=date
            )
        elif date and (existing.observed_date is None or date < existing.observed_date):
            existing.rank = rank
            existing.observed_date = date
            existing.save(update_fields=["rank", "observed_date"])
