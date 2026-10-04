"""Incremental rating: replay only the rating periods that changed.

Ratings are tournament-locked, so the stored ratings are the result of
applying periods (tournaments) in a fixed order. When new matches arrive
they almost always belong to the newest periods — a new tournament, or an
ongoing one gaining matches. `rate` then:

  1. fingerprints every period and compares with RatedPeriod;
  2. if every changed period sits at the TAIL of the processing order, rolls
     the already-rated ones back with their undo logs (RatingUndo) and
     replays the tail from that state;
  3. otherwise (a backfilled old tournament, a change past the undo window,
     new settings or seed ranks, a removed period) falls back to a full
     rebuild.

The engine guarantees resumed == full (rating.run(initial=...), rollback),
so both paths store identical ratings. `rate --rebuild` stays the reference.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from rating import Rating
from rating.run import _MIN_TS, period_sort_key

from .models import RatedPeriod, RatingState, RatingUndo


def _sha(obj) -> str:
    return hashlib.sha1(repr(obj).encode()).hexdigest()


def fingerprint(period) -> str:
    """Hash of everything the engine reads from a period's matches."""
    return _sha(sorted(period, key=lambda m: m.match_id))


def config_hash(config) -> str:
    return _sha(config)


def seeds_hash(seeds) -> str:
    return _sha(sorted(seeds.items()))


def undo_boundary(periods, days: int):
    """Periods starting on/after this keep an undo log."""
    starts = [period_sort_key(ms)[0] for _, ms in periods]
    latest = max((s for s in starts if s != _MIN_TS), default=None)
    return latest - timedelta(days=days) if latest else None


@dataclass
class Plan:
    mode: str  # "full" | "incremental" | "noop"
    reason: str = ""
    first: int = 0  # index of the first period to replay
    rolled: list[int] | None = None  # rated tids to roll back, oldest first


def plan(periods, fps, cfg_hash: str, sd_hash: str) -> Plan:
    state = RatingState.objects.filter(pk=1).first()
    if state is None:
        return Plan("full", "no stored rating state")
    if state.config_hash != cfg_hash:
        return Plan("full", "rating settings changed")
    if state.seeds_hash != sd_hash:
        return Plan("full", "seed ranks changed")

    rated = {r.tournament_id: r for r in RatedPeriod.objects.all()}
    current = {tid for tid, _ in periods}
    if set(rated) - current:
        return Plan("full", "a rated tournament was removed")
    changed = [i for i, (tid, _) in enumerate(periods)
               if tid not in rated or rated[tid].fingerprint != fps[tid]]
    if not changed:
        return Plan("noop", "ratings are up to date")

    first = changed[0]
    replay = [tid for tid, _ in periods[first:]]
    rolled = [tid for tid in replay if tid in rated]
    # The rated periods being replayed must be exactly the newest ones in the
    # OLD processing order — otherwise rolling them back can't restore the
    # state they were applied on.
    old_order = sorted(
        rated.values(),
        key=lambda r: (r.start_ts or _MIN_TS, r.start_round, r.start_match),
    )
    tail = [r.tournament_id for r in old_order[len(old_order) - len(rolled):]] if rolled else []
    if set(tail) != set(rolled):
        return Plan("full", "a change reaches before newer rated tournaments")
    if rolled:
        logged = set(
            RatingUndo.objects.filter(tournament_id__in=rolled)
            .values_list("tournament_id", flat=True).distinct()
        )
        if set(rolled) - logged:
            return Plan("full", "a changed tournament is older than the undo window")
    return Plan("incremental", f"replaying {len(replay)} tournament(s)", first, tail)


def load_ratings() -> dict[tuple[int, str], Rating]:
    from .models import PlayerRating

    return {
        (pid, ev): Rating(mu=mu, rd=rd, sigma=sigma, matches_played=n, last_match_utc=last)
        for pid, ev, mu, rd, sigma, n, last in PlayerRating.objects.values_list(
            "player_id", "event", "mu", "rd", "sigma", "matches_played", "last_match_utc"
        ).iterator()
    }


def load_undo(tids: list[int]) -> list[dict]:
    """Undo logs for `tids`, in the given (processing) order."""
    logs: dict[int, dict] = {tid: {} for tid in tids}
    for row in RatingUndo.objects.filter(tournament_id__in=tids).iterator():
        logs[row.tournament_id][(row.player_id, row.event)] = (
            Rating(mu=row.mu, rd=row.rd, sigma=row.sigma,
                   matches_played=row.matches_played, last_match_utc=row.last_match_utc)
            if row.existed else None
        )
    return [logs[tid] for tid in tids]


def save_state(periods, fps, cfg_hash, sd_hash, undo, boundary, replaced=None):
    """Record which periods the stored ratings include, and their undo logs.

    replaced=None: the ratings were rebuilt from scratch (replace everything);
    else the list of tids that were (re)applied this run.
    """
    by_tid = dict(periods)
    tids = list(by_tid) if replaced is None else replaced
    if replaced is None:
        RatedPeriod.objects.all().delete()
        RatingUndo.objects.all().delete()
    else:
        RatedPeriod.objects.filter(tournament_id__in=tids).delete()
        RatingUndo.objects.filter(tournament_id__in=tids).delete()
    rows = []
    for tid in tids:
        ts, rnd, mid = period_sort_key(by_tid[tid])
        rows.append(RatedPeriod(
            tournament_id=tid, fingerprint=fps[tid],
            start_ts=None if ts == _MIN_TS else ts, start_round=rnd, start_match=mid,
        ))
    RatedPeriod.objects.bulk_create(rows, batch_size=2000)
    RatingUndo.objects.bulk_create(
        [
            RatingUndo(
                tournament_id=tid, player_id=pid, event=ev, existed=prior is not None,
                mu=prior.mu if prior else None, rd=prior.rd if prior else None,
                sigma=prior.sigma if prior else None,
                matches_played=prior.matches_played if prior else 0,
                last_match_utc=prior.last_match_utc if prior else None,
            )
            for tid, log in undo.items()
            for (pid, ev), prior in log.items()
        ],
        batch_size=5000,
    )
    if boundary is not None:
        # Logs that fell out of the window are never needed again.
        old = RatedPeriod.objects.filter(start_ts__lt=boundary).values_list(
            "tournament_id", flat=True
        )
        RatingUndo.objects.filter(tournament_id__in=list(old)).delete()
    RatingState.objects.update_or_create(
        pk=1, defaults={"config_hash": cfg_hash, "seeds_hash": sd_hash,
                        "updated_utc": timezone.now()},
    )


def clear_state():
    """Forget the bookkeeping (e.g. after a --event run): next rate is full."""
    RatingState.objects.all().delete()
    RatedPeriod.objects.all().delete()
    RatingUndo.objects.all().delete()
