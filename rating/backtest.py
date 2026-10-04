"""Backtest harness — score how well a rating engine PREDICTS results. Pure.

Runs an engine over the full chronological match stream, then grades every
match on/after `since` using the ratings each player held going INTO that
match (`RatingDelta.mu_before / rd_before` — the tournament-locked figure the
engine actually had). A setting or engine change ships only if it beats the
baseline here on held-out log-loss.

Metrics (lower is better unless noted):
  * log_loss  — mean negative log-likelihood of the actual winner
  * brier     — mean squared error of the predicted probability
  * accuracy  — share of matches the favourite won (higher is better)
  * ece       — expected calibration error over 10 probability buckets

No Django imports: `manage.py backtest` feeds this the same records `rate` uses.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .predict import team_rating, win_probability
from .run import RunResult, run
from .types import MatchRecord, RatingConfig

_EPS = 1e-6

Engine = Callable[..., RunResult]


@dataclass
class Bucket:
    n: int = 0
    prob_sum: float = 0.0
    correct: int = 0


@dataclass
class BacktestResult:
    n: int
    log_loss: float
    brier: float
    accuracy: float
    ece: float
    buckets: list[Bucket] = field(default_factory=list)

    def row(self, label: str) -> str:
        return (
            f"{label:40s} n={self.n:<7d} logloss={self.log_loss:.4f} "
            f"brier={self.brier:.4f} acc={self.accuracy:.4f} ece={self.ece:.4f}"
        )


def score(
    matches: list[MatchRecord],
    result: RunResult,
    since: datetime | None = None,
    until: datetime | None = None,
) -> BacktestResult:
    """Grade the pre-match predictions in `result.history` for matches in
    [since, until)."""
    pre: dict[int, dict[int, tuple[float, float]]] = {}
    for d in result.history:
        pre.setdefault(d.match_id, {})[d.player_id] = (d.mu_before, d.rd_before)

    ll = br = 0.0
    n = acc = 0
    buckets = [Bucket() for _ in range(10)]
    for m in matches:
        if m.match_id not in pre or m.winner_side not in (1, 2):
            continue
        t = m.match_time_utc
        if since is not None and (t is None or t < since):
            continue
        if until is not None and (t is None or t >= until):
            continue
        players = pre[m.match_id]
        t1 = team_rating([players[p] for p in m.side1_player_ids if p in players])
        t2 = team_rating([players[p] for p in m.side2_player_ids if p in players])
        if not t1 or not t2:
            continue
        p = win_probability(t1[0], t1[1], t2[0], t2[1])
        p = min(max(p, _EPS), 1.0 - _EPS)
        y = 1.0 if m.winner_side == 1 else 0.0
        ll -= y * math.log(p) + (1.0 - y) * math.log(1.0 - p)
        br += (p - y) ** 2
        n += 1
        fav_won = (p >= 0.5) == (y == 1.0)
        acc += fav_won
        fav_p = max(p, 1.0 - p)
        b = buckets[min(9, int(fav_p * 10))]
        b.n += 1
        b.prob_sum += fav_p
        b.correct += fav_won

    if n == 0:
        return BacktestResult(0, math.nan, math.nan, math.nan, math.nan, buckets)
    ece = sum(abs(b.prob_sum / b.n - b.correct / b.n) * b.n for b in buckets if b.n) / n
    return BacktestResult(n, ll / n, br / n, acc / n, ece, buckets)


def backtest(
    matches: list[MatchRecord],
    config: RatingConfig,
    *,
    seed_ranks=None,
    since: datetime | None = None,
    until: datetime | None = None,
    engine: Engine = run,
) -> BacktestResult:
    """Run `engine` over `matches` and score predictions in [since, until)."""
    result = engine(matches, config, seed_ranks=seed_ranks)
    return score(matches, result, since=since, until=until)
