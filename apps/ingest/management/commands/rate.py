"""`manage.py rate` — the ONLY bridge between the DB and the pure rating engine.

Reads normalized matches out of the ORM, converts them to plain
`rating.MatchRecord` dataclasses (resolving each match's tier weight from
settings), runs the engine chronologically, and writes PlayerRating +
RatingHistory back. The engine itself never touches Django.

`rate` and `rate --rebuild` both do a full deterministic recompute (PRD §7.7):
running twice yields identical ratings. (Incremental resume is a future
optimization; a from-scratch recompute is the correctness baseline.)

    python manage.py rate
    python manage.py rate --rebuild
    python manage.py rate --event XD        # limit to one discipline
"""
from __future__ import annotations

import re
from datetime import datetime, time, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import Game, Match, MatchPlayer, PlayerRating, RatingHistory
from rating import GameRecord, MatchRecord, RatingConfig, run

# "HSBC BWF World Tour Super 500" -> "Super500" (key into TIER_WEIGHTS).
_TIER_RE = re.compile(r"(Super\s?\d+|Finals)", re.IGNORECASE)


def _tier_weight(category_name: str, weights: dict) -> float:
    if not category_name:
        return 1.0
    m = _TIER_RE.search(category_name)
    if not m:
        return 1.0
    key = m.group(1).replace(" ", "")
    return weights.get(key, 1.0)


def _effective_ts(match) -> datetime | None:
    """Ordering timestamp: the real match time, else the tournament start date.

    56%+ of historical matches carry no matchTimeUtc; falling back to the
    tournament date keeps cross-tournament chronology (refined within a
    tournament by round_order + match_id, applied by the engine's sort key).
    """
    if match.match_time_utc is not None:
        return match.match_time_utc
    start = match.tournament.start_date
    if start is not None:
        return datetime.combine(start, time.min, tzinfo=timezone.utc)
    return None


def _config() -> RatingConfig:
    r = settings.RATING
    return RatingConfig(
        mu_init=r["MU_INIT"],
        rd_init=r["RD_INIT"],
        sigma_init=r["SIGMA_INIT"],
        tau=r["TAU"],
        pair_blend=r["PAIR_BLEND"],
        lambda_=r["LAMBDA"],
        m_min=r["M_MIN"],
        m_max=r["M_MAX"],
        d_floor=r["D_FLOOR"],
        k_retire=r["K_RETIRE"],
        rd_inflate_c=r["RD_INFLATE_C"],
        tier_weights=r["TIER_WEIGHTS"],
    )


class Command(BaseCommand):
    help = "Compute per-(player, discipline) ratings from ingested matches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Deterministic recompute from scratch (default behaviour too).",
        )
        parser.add_argument("--event", default=None, help="Limit to one discipline.")
        parser.add_argument(
            "--batch-size", type=int, default=2000, help="Bulk write batch size."
        )

    def handle(self, *args, **opts):
        weights = settings.RATING["TIER_WEIGHTS"]
        records = self._load_matches(opts["event"], weights)
        self.stdout.write(f"Loaded {len(records)} rated matches; running engine…")

        result = run(records, _config())
        self.stdout.write(
            f"Computed {len(result.ratings)} (player, event) ratings, "
            f"{len(result.history)} history rows."
        )
        self._write(result, opts["event"], opts["batch_size"])
        self.stdout.write(self.style.SUCCESS("rate complete."))

    # -- read ---------------------------------------------------------------
    def _load_matches(self, event, weights) -> list[MatchRecord]:
        qs = Match.objects.filter(rating_excluded=False, winner_side__in=[1, 2])
        if event:
            qs = qs.filter(event=event)
        qs = qs.select_related("tournament")

        # Group lineups and games once to avoid per-match queries.
        lineups: dict[int, dict[int, list[int]]] = {}
        mp = MatchPlayer.objects.values_list("match_id", "side", "player_id")
        if event:
            mp = mp.filter(match__event=event)
        for match_id, side, player_id in mp.iterator():
            lineups.setdefault(match_id, {1: [], 2: []})[side].append(player_id)

        games: dict[int, list[GameRecord]] = {}
        gq = Game.objects.values_list(
            "match_id", "game_no", "side1_points", "side2_points"
        )
        if event:
            gq = gq.filter(match__event=event)
        for match_id, game_no, s1, s2 in gq.iterator():
            games.setdefault(match_id, []).append(GameRecord(game_no, s1, s2))

        records = []
        for m in qs.iterator():
            line = lineups.get(m.match_id)
            if not line or not line.get(1) or not line.get(2):
                continue  # need both sides to rate
            g = sorted(games.get(m.match_id, []), key=lambda x: x.game_no)
            records.append(
                MatchRecord(
                    match_id=m.match_id,
                    event=m.event,
                    match_time_utc=_effective_ts(m),
                    round_order=m.round_order,
                    winner_side=m.winner_side,
                    score_status=m.score_status,
                    scoring_format=m.scoring_format,
                    rating_excluded=m.rating_excluded,
                    side1_player_ids=tuple(sorted(line[1])),
                    side2_player_ids=tuple(sorted(line[2])),
                    games=tuple(g),
                    tier_weight=_tier_weight(m.tournament.category_name, weights),
                    tournament_id=m.tournament_id,
                )
            )
        return records

    # -- write --------------------------------------------------------------
    @transaction.atomic
    def _write(self, result, event, batch_size):
        # Full recompute: clear prior outputs (scoped to --event if given).
        ph = PlayerRating.objects.all()
        rh = RatingHistory.objects.all()
        if event:
            ph = ph.filter(event=event)
            rh = rh.filter(event=event)
        rh.delete()
        ph.delete()

        # Peak = highest mu_after ever reached per (player, event), with the
        # rd/date at that moment. Built from the history stream.
        peak: dict[tuple[int, str], tuple[float, float, object]] = {}
        for d in result.history:
            key = (d.player_id, d.event)
            best = peak.get(key)
            if best is None or d.mu_after > best[0]:
                peak[key] = (d.mu_after, d.rd_after, d.applied_utc)

        PlayerRating.objects.bulk_create(
            [
                PlayerRating(
                    player_id=pid,
                    event=ev,
                    mu=r.mu,
                    rd=r.rd,
                    sigma=r.sigma,
                    matches_played=r.matches_played,
                    last_match_utc=r.last_match_utc,
                    peak_mu=peak.get((pid, ev), (r.mu, r.rd, r.last_match_utc))[0],
                    peak_rd=peak.get((pid, ev), (r.mu, r.rd, r.last_match_utc))[1],
                    peak_utc=peak.get((pid, ev), (r.mu, r.rd, r.last_match_utc))[2],
                )
                for (pid, ev), r in result.ratings.items()
            ],
            batch_size=batch_size,
        )
        RatingHistory.objects.bulk_create(
            [
                RatingHistory(
                    player_id=d.player_id,
                    event=d.event,
                    match_id=d.match_id,
                    mu_before=d.mu_before,
                    mu_after=d.mu_after,
                    rd_before=d.rd_before,
                    rd_after=d.rd_after,
                    delta=d.delta,
                    applied_utc=d.applied_utc,
                )
                for d in result.history
            ],
            batch_size=batch_size,
        )
