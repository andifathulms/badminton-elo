"""`manage.py rate_history` — smoothed all-time ratings (run after `rate`).

Fits TrueSkill Through Time per discipline over every match
(rating/history.py), calibrates it to the live rating scale, and stores each
player's year-end smoothed skill (SmoothedRating) and all-time best on
PlayerRating (alltime_*), which the "All-time peak" board ranks by. ~4-5
minutes on the full data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.db import transaction

from apps.ingest.management.base import DataCommand
from apps.ingest.management.commands.rate import load_records
from apps.ingest.models import PlayerRating, SmoothedRating
from rating.history import best_point, fit_scale, rescale, smooth

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _date(day: float) -> date:
    return (_EPOCH + timedelta(days=day)).date()


# Players whose live rating anchors the smoothed -> live scale fit.
ANCHOR_MIN_MATCHES = 20
ANCHOR_MAX_RD = 100.0
ANCHOR_MIN_PLAYERS = 30


class Command(DataCommand):
    help = "Smooth every discipline's history (TrueSkill Through Time)."

    def _calibrate(self, curves):
        """Map each discipline's smoothed curves onto its live rating scale,
        fitted on settled players (latest smoothed skill vs live rating)."""
        live = {
            (pid, ev): mu
            for pid, ev, mu in PlayerRating.objects.filter(
                matches_played__gte=ANCHOR_MIN_MATCHES, rd__lte=ANCHOR_MAX_RD
            ).values_list("player_id", "event", "mu")
        }
        by_event = defaultdict(list)
        for key, curve in curves.items():
            if key in live:
                by_event[key[1]].append((curve[-1][1], live[key]))
        pooled = fit_scale([pr for prs in by_event.values() for pr in prs])
        fits = {
            ev: fit_scale(prs) if len(prs) >= ANCHOR_MIN_PLAYERS else pooled
            for ev, prs in by_event.items()
        }
        return {key: rescale(curve, *fits.get(key[1], pooled)) for key, curve in curves.items()}

    def handle(self, *args, **opts):
        p = settings.HISTORY_ENGINE
        curves = smooth(load_records(), sigma=p["SIGMA"], gamma=p["GAMMA"],
                        beta=p["BETA"], iterations=p["ITERATIONS"])
        curves = self._calibrate(curves)

        yearly = []
        for (pid, event), curve in curves.items():
            last_in_year = {}
            for day, mu, rd in curve:
                last_in_year[_date(day).year] = (mu, rd)
            yearly += [SmoothedRating(player_id=pid, event=event, year=y, mu=mu, rd=rd)
                       for y, (mu, rd) in last_in_year.items()]

        rows = list(PlayerRating.objects.only("id", "player_id", "event"))
        for r in rows:
            curve = curves.get((r.player_id, r.event))
            if curve:
                day, r.alltime_mu, r.alltime_rd = best_point(curve)
                r.alltime_date = _date(day)
            else:
                r.alltime_mu = r.alltime_rd = r.alltime_date = None

        with transaction.atomic():
            SmoothedRating.objects.all().delete()
            SmoothedRating.objects.bulk_create(yearly, batch_size=5000)
            PlayerRating.objects.bulk_update(
                rows, ["alltime_mu", "alltime_rd", "alltime_date"], batch_size=2000
            )
        self.stdout.write(self.style.SUCCESS(
            f"smoothed {len(curves)} (player, event) histories; {len(yearly)} year points."
        ))
