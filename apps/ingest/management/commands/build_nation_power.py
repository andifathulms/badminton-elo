"""`manage.py build_nation_power` — per-discipline national strength over time.

For each discipline (MS/WS/MD/WD/XD) and year, reconstruct every player's rating
as of that year-end (their last rating before Dec 31, active within the prior
year), then sum each country's top-3 players. That per-year, per-country power is
the raw material for dominance eras / dynasties — which nation ruled which
discipline in which years. Run after `rate`.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import NationYear, Player, RatingHistory

EVENTS = ("MS", "WS", "MD", "WD", "XD")
TOP = 3            # players summed per country
MIN_PLAYERS = 2    # need at least this many to rank (avoids single-star noise)


class Command(BaseCommand):
    help = "Reconstruct per-year national strength per discipline from RatingHistory."

    def handle(self, *args, **opts):
        series: dict = defaultdict(list)  # (pid, event) -> sorted [(date, mu)]
        for pid, ev, applied, mu in RatingHistory.objects.filter(
            event__in=EVENTS
        ).values_list("player_id", "event", "applied_utc", "mu_after").iterator():
            if applied is not None:
                series[(pid, ev)].append((applied, mu))
        for k in series:
            series[k].sort()

        country = dict(Player.objects.values_list("player_id", "country_code"))
        years = {d.year for lst in series.values() for d, _ in (lst[:1] + lst[-1:])}
        if not years:
            self.stdout.write("no dated history; nothing to build.")
            return

        rows = []
        for year in range(min(years), max(years) + 1):
            asof = datetime(year, 12, 31, tzinfo=timezone.utc)
            active_from = asof - timedelta(days=365)
            per: dict = defaultdict(lambda: defaultdict(list))  # event -> cc -> [mu]
            for (pid, ev), pts in series.items():
                idx = bisect.bisect_right(pts, (asof, float("inf"))) - 1
                if idx < 0:
                    continue
                last_date, mu = pts[idx]
                if last_date < active_from:
                    continue
                cc = country.get(pid)
                if cc:
                    per[ev][cc].append(mu)

            for ev in EVENTS:
                for cc, mus in per[ev].items():
                    if len(mus) < MIN_PLAYERS:
                        continue
                    top = sorted(mus, reverse=True)[:TOP]
                    rows.append(
                        NationYear(event=ev, country=cc, year=year,
                                   power=round(sum(top), 1), players=len(top))
                    )

        with transaction.atomic():
            NationYear.objects.all().delete()
            NationYear.objects.bulk_create(rows, batch_size=5000)
        self.stdout.write(self.style.SUCCESS(f"built {len(rows)} nation-year rows."))
