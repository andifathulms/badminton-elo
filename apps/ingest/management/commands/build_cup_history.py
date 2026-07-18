"""`manage.py build_cup_history` — national team power over time.

Reconstructs each player's rating as of each year-end from RatingHistory (their
last rating before that date), keeps only players active within the prior year,
and sums each country's top players per cup discipline — so the Cups timeline
shows which nations were dominant in which era. Uses individual ratings (top-K
players per event) as the team-strength proxy. Run after `rate`.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingest.models import CupPowerHistory, Player, RatingHistory

# Individual-based team composition (2 players per doubles pair-slot).
CUP_SPECS = {
    "thomas": [("MS", 3), ("MD", 4)],
    "uber": [("WS", 3), ("WD", 4)],
    "sudirman": [("MS", 1), ("WS", 1), ("MD", 2), ("WD", 2), ("XD", 2)],
}


class Command(BaseCommand):
    help = "Reconstruct per-year national team power per cup from RatingHistory."

    def handle(self, *args, **opts):
        # Per (player, event): sorted (date, mu) history.
        series: dict = defaultdict(list)
        for pid, ev, applied, mu in RatingHistory.objects.values_list(
            "player_id", "event", "applied_utc", "mu_after"
        ).iterator():
            if applied is not None:
                series[(pid, ev)].append((applied, mu))
        for k in series:
            series[k].sort()

        country = dict(Player.objects.values_list("player_id", "country_code"))

        years_present = {
            d.year for lst in series.values() for d, _ in (lst[:1] + lst[-1:])
        }
        if not years_present:
            self.stdout.write("no dated history; nothing to build.")
            return
        y0, y1 = min(years_present), max(years_present)

        rows = []
        for year in range(y0, y1 + 1):
            asof = datetime(year, 12, 31, tzinfo=timezone.utc)
            active_from = asof - timedelta(days=365)
            # event -> country -> [ratings of active players as of `asof`]
            per: dict = defaultdict(lambda: defaultdict(list))
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

            for cup, spec in CUP_SPECS.items():
                # candidate countries: those with players in every event
                countries = set.intersection(
                    *[set(per[ev].keys()) for ev, _ in spec]
                ) if all(per[ev] for ev, _ in spec) else set()
                for cc in countries:
                    power, ok = 0.0, True
                    for ev, count in spec:
                        top = sorted(per[ev][cc], reverse=True)[:count]
                        if len(top) < count:
                            ok = False
                            break
                        power += sum(top)
                    if ok:
                        rows.append(
                            CupPowerHistory(
                                cup=cup, country=cc, year=year, power=round(power)
                            )
                        )

        with transaction.atomic():
            CupPowerHistory.objects.all().delete()
            CupPowerHistory.objects.bulk_create(rows, batch_size=5000)
        self.stdout.write(
            self.style.SUCCESS(f"built {len(rows)} cup-power history rows.")
        )
