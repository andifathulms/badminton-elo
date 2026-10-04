"""`manage.py rate` — the ONLY bridge between the DB and the pure rating engine.

Reads normalized matches out of the ORM, converts them to plain
`rating.MatchRecord` dataclasses (resolving each match's tier weight from
settings), runs the engine chronologically, and writes PlayerRating +
RatingHistory back. The engine itself never touches Django.

`rate` is incremental: it replays only the tournaments that changed when they
are the newest ones (apps/ingest/incremental.py), and rebuilds from scratch
otherwise. `rate --rebuild` always recomputes from scratch — the deterministic
reference (PRD §7.7); both give identical ratings.

    python manage.py rate
    python manage.py rate --rebuild
    python manage.py rate --event XD        # one discipline, from scratch
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from django.conf import settings
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Max, Sum, When

from apps.ingest import incremental
from apps.ingest.boards import ACTIVE_DAYS, BOARD_MIN_MATCHES, FORM_POINTS, board_ranks
from apps.ingest.management.base import DataCommand
from apps.ingest.models import (
    Game,
    Match,
    MatchPlayer,
    Player,
    PlayerRating,
    RatingHistory,
)
from rating import GameRecord, MatchRecord, RatingConfig, group_periods, rollback, run
from rating.peaks import peak_ratings
from rating.types import RatingDelta

# Prestige grade per tournament category (key into TIER_WEIGHTS). Every
# category the data holds maps to one grade, so the World Championships or a
# Superseries Premier can never weigh less than a Super 1000. Unlisted -> "low".
TIER_GRADES = {
    "major": (
        "Olympics", "World Championships", "HSBC BWF World Tour Finals",
        "HSBC BWF World Tour Super 1000", "All England",
        "World Superseries Premier", "Thomas Cup", "Uber Cup", "Sudirman Cup",
    ),
    "high": (
        "HSBC BWF World Tour Super 750", "HSBC BWF World Tour Super 500",
        "World Superseries", "Super Series", "Grand Prix Gold", "Asian Games",
        "Commonwealth Games", "Continental Individual Championships",
        "Grade 1 – Individual Tournaments", "Grade 1 – Team Tournaments",
    ),
    "mid": (
        "HSBC BWF World Tour Super 300", "BWF Tour Super 100", "Grand Prix",
        "Continental Team Championships", "SEA Games", "European Games",
        "Pan American Games", "African Games", "Continental Individual Games",
        "Continental Team Games",
    ),
}
_GRADE_OF = {cat: grade for grade, cats in TIER_GRADES.items() for cat in cats}


def tier_grade(category_name: str) -> str:
    return _GRADE_OF.get((category_name or "").strip(), "low")


def _tier_weight(category_name: str, weights: dict) -> float:
    return weights.get(tier_grade(category_name), 1.0)


_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


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


def _config(overrides: dict | None = None) -> RatingConfig:
    """settings.RATING -> RatingConfig. `overrides` (same keys) win, for backtests."""
    r = {**settings.RATING, **(overrides or {})}
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
        seed_rank_top_mu=r["SEED_RANK_TOP_MU"],
        seed_rank_base=r["SEED_RANK_BASE"],
        seed_rd=r["SEED_RD"],
        cross_prior_weight=r.get("CROSS_PRIOR_WEIGHT", 0.0),
        cross_prior_rd=r.get("CROSS_PRIOR_RD", 250.0),
        cross_prior_min_matches=r.get("CROSS_PRIOR_MIN_MATCHES", 5),
    )


def load_seed_ranks(event=None) -> dict[tuple[int, str], tuple[int, object]]:
    """(player_id, event) -> (rank, observed_date). The engine only uses a rank
    observed by the player's first period, so a later ranking can't leak back."""
    from apps.ingest.models import PlayerSeedRank

    qs = PlayerSeedRank.objects.all()
    if event:
        qs = qs.filter(event=event)
    return {
        (pid, ev): (rank, observed)
        for pid, ev, rank, observed in qs.values_list(
            "player_id", "event", "rank", "observed_date"
        )
    }


def load_records(event=None, weights=None) -> list[MatchRecord]:
    """ORM rows -> engine MatchRecords (lineups/games grouped in 3 queries)."""
    if weights is None:
        weights = settings.RATING["TIER_WEIGHTS"]
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


def win_loss_records(event=None, player_ids=None) -> dict[tuple[int, str], tuple[int, int]]:
    """(player, event) -> (wins, losses) over every match in the discipline
    (walkovers included — the record a fan reads, not just rated matches)."""
    qs = MatchPlayer.objects.all()
    if event:
        qs = qs.filter(match__event=event)
    if player_ids is not None:
        qs = qs.filter(player_id__in=list(player_ids))
    rows = (
        qs.values("player_id", "match__event")
        .annotate(
            played=Count("id"),
            won=Sum(Case(When(side=F("match__winner_side"), then=1),
                         default=0, output_field=IntegerField())),
        )
        .order_by()
    )
    return {
        (r["player_id"], r["match__event"]): (r["won"] or 0, r["played"] - (r["won"] or 0))
        for r in rows.iterator()
    }


def form_lines(history) -> dict[tuple[int, str], list[int]]:
    """(player, event) -> the rating carried into each of the last FORM_POINTS
    tournaments (ratings are tournament-locked, so one value per period)."""
    rows = defaultdict(list)
    for d in history:
        rows[(d.player_id, d.event)].append((d.applied_utc or _MIN_TS, d.match_id, d.mu_before))
    out = {}
    for key, seq in rows.items():
        seq.sort(key=lambda x: (x[0], x[1]))
        starts: list[float] = []
        for _, _, mu_b in seq:
            if not starts or starts[-1] != mu_b:
                starts.append(mu_b)
        out[key] = [round(x) for x in starts[-FORM_POINTS:]]
    return out


def current_board_ranks(ratings, event=None):
    """Ranks on the default current board (apps.ingest.boards), per event and
    within gender. Written by `rate` so the board is never blank between `rate`
    and `build_movement` (which adds the 4-weeks-ago ranks)."""
    latest = max((r.last_match_utc for r in ratings.values() if r.last_match_utc),
                 default=None)
    others = PlayerRating.objects.exclude(event=event) if event else PlayerRating.objects.none()
    other_latest = others.aggregate(m=Max("last_match_utc"))["m"]
    if other_latest and (latest is None or other_latest > latest):
        latest = other_latest
    if latest is None:
        return {}, {}
    cut = latest - timedelta(days=ACTIVE_DAYS)
    gender = dict(Player.objects.exclude(gender="").values_list("player_id", "gender"))
    by_event = defaultdict(list)
    for (pid, ev), r in ratings.items():
        if r.matches_played >= BOARD_MIN_MATCHES and r.last_match_utc and r.last_match_utc >= cut:
            by_event[ev].append((pid, gender.get(pid, ""), r.mu - 2.0 * r.rd))
    ranks, ranks_g = {}, {}
    for ev, rows in by_event.items():
        overall, within = board_ranks(rows)
        ranks.update({(p, ev): v for p, v in overall.items()})
        ranks_g.update({(p, ev): v for p, v in within.items()})
    return ranks, ranks_g


class Command(DataCommand):
    help = "Compute per-(player, discipline) ratings from ingested matches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Recompute everything from scratch (the deterministic reference).",
        )
        parser.add_argument("--event", default=None, help="Limit to one discipline.")
        parser.add_argument(
            "--batch-size", type=int, default=2000, help="Bulk write batch size."
        )

    def handle(self, *args, **opts):
        weights = settings.RATING["TIER_WEIGHTS"]
        event = opts["event"]
        config = _config()
        records = load_records(event, weights)
        seed_ranks = load_seed_ranks(event)
        self.stdout.write(f"Loaded {len(records)} rated matches, {len(seed_ranks)} seed ranks.")

        if event:
            # One discipline from scratch; the incremental bookkeeping covers
            # all disciplines, so forget it (the next plain `rate` is full).
            result = run(records, config, seed_ranks=seed_ranks)
            with transaction.atomic():
                self._write(result, event, opts["batch_size"])
                incremental.clear_state()
            self.stdout.write(self.style.SUCCESS(f"rate complete ({event}, from scratch)."))
            return

        periods = group_periods(records)
        fps = {tid: incremental.fingerprint(ms) for tid, ms in periods}
        cfg_hash = incremental.config_hash(config)
        sd_hash = incremental.seeds_hash(seed_ranks)
        boundary = incremental.undo_boundary(periods, settings.RATING.get("UNDO_DAYS", 120))
        plan = (
            incremental.Plan("full", "--rebuild") if opts["rebuild"]
            else incremental.plan(periods, fps, cfg_hash, sd_hash)
        )
        self.stdout.write(f"Plan: {plan.mode} ({plan.reason}).")
        if plan.mode == "noop":
            self.stdout.write(self.style.SUCCESS("rate complete (nothing changed)."))
            return

        if plan.mode == "incremental":
            start = rollback(incremental.load_ratings(), incremental.load_undo(plan.rolled))
            replay = periods[plan.first:]
            result = run(
                [m for _, ms in replay for m in ms], config,
                seed_ranks=seed_ranks, initial=start, undo_since=boundary,
            )
            with transaction.atomic():
                self._write_incremental(result, start, [t for t, _ in replay], plan.rolled,
                                        opts["batch_size"])
                incremental.save_state(periods, fps, cfg_hash, sd_hash, result.undo, boundary,
                                       replaced=[t for t, _ in replay])
            self.stdout.write(self.style.SUCCESS(
                f"rate complete: replayed {len(replay)} tournament(s), "
                f"{len(result.history)} history rows."
            ))
            return

        result = run(records, config, seed_ranks=seed_ranks, undo_since=boundary)
        self.stdout.write(
            f"Computed {len(result.ratings)} (player, event) ratings, "
            f"{len(result.history)} history rows."
        )
        with transaction.atomic():
            self._write(result, None, opts["batch_size"])
            incremental.save_state(periods, fps, cfg_hash, sd_hash, result.undo, boundary)
        self.stdout.write(self.style.SUCCESS("rate complete."))

    # -- write --------------------------------------------------------------
    # Callers own the transaction: a nested atomic() here would be a SAVEPOINT,
    # which on SQLite copies every page of the 1M-row rewrite (~3x slower).
    def _write(self, result, event, batch_size):
        # Full recompute: clear prior outputs (scoped to --event if given).
        ph = PlayerRating.objects.all()
        rh = RatingHistory.objects.all()
        if event:
            ph = ph.filter(event=event)
            rh = rh.filter(event=event)
        rh.delete()
        ph.delete()

        # Peak = highest settled mu (rd <= PEAK_MAX_RD) per (player, event), with
        # the rd/date at that moment. See rating.peaks.
        peak = peak_ratings(result.history, settings.RATING.get("PEAK_MAX_RD", 100.0))
        record = win_loss_records(event)
        form = form_lines(result.history)
        ranks, ranks_g = current_board_ranks(result.ratings, event)

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
                    wins=record.get((pid, ev), (0, 0))[0],
                    losses=record.get((pid, ev), (0, 0))[1],
                    form=form.get((pid, ev), []),
                    rank=ranks.get((pid, ev)),
                    rank_gender=ranks_g.get((pid, ev)),
                )
                for (pid, ev), r in result.ratings.items()
            ],
            batch_size=batch_size,
        )
        _bulk_history(result.history, batch_size)

    def _write_incremental(self, result, start, replay_tids, rolled_tids, batch_size):
        """Swap the replayed tournaments' history and update only the ratings
        they touch (plus everyone's board rank, which can shift)."""
        RatingHistory.objects.filter(match__tournament_id__in=replay_tids).delete()
        _bulk_history(result.history, batch_size)

        before = incremental.load_ratings()  # still the pre-replay rows
        touched = {(d.player_id, d.event) for d in result.history}
        touched |= {k for k in before if k not in start}  # first seen in a rolled period
        gone = [k for k in touched if k not in result.ratings]

        # Peaks and form from each touched rating's full stored history.
        hist = [
            RatingDelta(player_id=pid, event=ev, match_id=mid, mu_before=mb, mu_after=ma,
                        rd_before=rb, rd_after=ra, delta=dl, applied_utc=at)
            for pid, ev, mid, mb, ma, rb, ra, dl, at in RatingHistory.objects.filter(
                player_id__in={p for p, _ in touched}
            ).order_by("applied_utc", "match_id").values_list(
                "player_id", "event", "match_id", "mu_before", "mu_after",
                "rd_before", "rd_after", "delta", "applied_utc",
            ).iterator()
            if (pid, ev) in touched
        ]
        peak = peak_ratings(hist, settings.RATING.get("PEAK_MAX_RD", 100.0))
        form = form_lines(hist)
        record = win_loss_records(player_ids={p for p, _ in touched})

        for pid, ev in gone:
            PlayerRating.objects.filter(player_id=pid, event=ev).delete()
        rows = {(r.player_id, r.event): r for r in PlayerRating.objects.filter(
            player_id__in={p for p, _ in touched})}
        new, upd = [], []
        for key in touched - set(gone):
            r = result.ratings[key]
            pr = rows.get(key) or PlayerRating(player_id=key[0], event=key[1])
            pk = peak.get(key, (r.mu, r.rd, r.last_match_utc))
            pr.mu, pr.rd, pr.sigma = r.mu, r.rd, r.sigma
            pr.matches_played, pr.last_match_utc = r.matches_played, r.last_match_utc
            pr.peak_mu, pr.peak_rd, pr.peak_utc = pk
            pr.wins, pr.losses = record.get(key, (0, 0))
            pr.form = form.get(key, [])
            (upd if pr.pk else new).append(pr)
        PlayerRating.objects.bulk_create(new, batch_size=batch_size)
        PlayerRating.objects.bulk_update(
            upd, ["mu", "rd", "sigma", "matches_played", "last_match_utc", "peak_mu",
                  "peak_rd", "peak_utc", "wins", "losses", "form"], batch_size=batch_size,
        )

        # Board ranks over everyone (a few new results can shift them all).
        everyone = incremental.load_ratings()
        ranks, ranks_g = current_board_ranks(everyone)
        stale = []
        for pr in PlayerRating.objects.only("id", "player_id", "event", "rank", "rank_gender"):
            key = (pr.player_id, pr.event)
            if (pr.rank, pr.rank_gender) != (ranks.get(key), ranks_g.get(key)):
                pr.rank, pr.rank_gender = ranks.get(key), ranks_g.get(key)
                stale.append(pr)
        PlayerRating.objects.bulk_update(stale, ["rank", "rank_gender"], batch_size=batch_size)


def _bulk_history(history, batch_size):
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
            for d in history
        ],
        batch_size=batch_size,
    )
