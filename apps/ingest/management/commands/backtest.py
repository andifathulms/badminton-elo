"""`manage.py backtest` — grade the rating engine's predictions (no writes).

Loads the same match records `rate` uses, runs the pure engine, and scores
every match on/after --since with the ratings held going into it (see
`rating.backtest`). Use it before changing any RATING setting: a change ships
only if it improves held-out log-loss.

    python manage.py backtest                         # current settings
    python manage.py backtest --set LAMBDA=1.0 --set D_FLOOR=0
    python manage.py backtest --no-seeds --since 2024-01-01
    python manage.py backtest --set ENGINE="'glicko'"   # compare engines
"""
from __future__ import annotations

import ast
import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.ingest.engine_config import rating_config as _config
from apps.ingest.management.commands.rate import load_records, load_seed_ranks
from rating.backtest import backtest


def _parse_override(raw: str) -> tuple[str, object]:
    if "=" not in raw:
        raise CommandError(f"--set expects KEY=VALUE, got {raw!r}")
    key, val = raw.split("=", 1)
    try:
        return key.strip().upper(), ast.literal_eval(val.strip())
    except (ValueError, SyntaxError) as exc:
        raise CommandError(f"bad value for {key}: {val!r}") from exc


class Command(BaseCommand):
    help = "Score the rating engine's pre-match predictions (log-loss/Brier/ECE)."

    def add_arguments(self, parser):
        parser.add_argument("--since", default="2023-01-01",
                            help="Score matches on/after this date (YYYY-MM-DD).")
        parser.add_argument("--until", default=None,
                            help="Stop scoring before this date (YYYY-MM-DD).")
        parser.add_argument("--event", default=None, help="Limit to one discipline.")
        parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                            help="Override a settings.RATING key for this run.")
        parser.add_argument("--no-seeds", action="store_true",
                            help="Ignore BWF ranking seeds (flat cold start).")


    def handle(self, *args, **opts):
        def _date(raw):
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        since = _date(opts["since"])
        until = _date(opts["until"]) if opts["until"] else None
        overrides = dict(_parse_override(s) for s in opts["set"])
        config = _config(overrides)

        t0 = time.monotonic()
        records = load_records(opts["event"], config.tier_weights)
        seeds = {} if opts["no_seeds"] else load_seed_ranks(opts["event"])
        self.stdout.write(f"loaded {len(records)} matches in {time.monotonic() - t0:.0f}s")

        t0 = time.monotonic()
        res = backtest(records, config, seed_ranks=seeds, since=since, until=until)
        label = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "current settings"
        label = f"[{config.engine}] {label}"
        if opts["no_seeds"]:
            label += " (no seeds)"
        self.stdout.write(res.row(label) + f"  ({time.monotonic() - t0:.0f}s)")
        for i, b in enumerate(res.buckets):
            if b.n:
                self.stdout.write(
                    f"  {i / 10:.1f}-{(i + 1) / 10:.1f}  n={b.n:<7d} "
                    f"predicted={b.prob_sum / b.n:.3f}  actual={b.correct / b.n:.3f}"
                )
