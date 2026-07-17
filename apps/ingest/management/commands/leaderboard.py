"""`manage.py leaderboard --event XD` — export a discipline ranking (PRD §10).

Reads PlayerRating (populated by `rate`) joined to Player. A conservative
ranking uses mu − 2·rd so an uncertain player can't top the list on a small
sample; pass --by-mu for raw skill instead.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ingest.models import PlayerRating


class Command(BaseCommand):
    help = "Print the leaderboard for a discipline (needs `rate` to have run)."

    def add_arguments(self, parser):
        parser.add_argument("--event", required=True, help="MS/WS/MD/WD/XD.")
        parser.add_argument("--top", type=int, default=25, help="Rows to show.")
        parser.add_argument(
            "--min-matches", type=int, default=5, help="Hide small samples."
        )
        parser.add_argument(
            "--by-mu",
            action="store_true",
            help="Rank by raw mu instead of the conservative mu-2*rd.",
        )

    def handle(self, *args, **opts):
        qs = (
            PlayerRating.objects.filter(
                event=opts["event"], matches_played__gte=opts["min_matches"]
            )
            .select_related("player")
        )
        rows = list(qs)
        if not rows:
            self.stderr.write(
                self.style.WARNING(
                    f"No ratings for {opts['event']} (run `manage.py rate` first)."
                )
            )
            return

        def score(r):
            return r.mu if opts["by_mu"] else r.mu - 2.0 * r.rd

        rows.sort(key=score, reverse=True)
        metric = "mu" if opts["by_mu"] else "mu-2rd"
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{opts['event']} leaderboard (by {metric}, "
                f"≥{opts['min_matches']} matches)"
            )
        )
        self.stdout.write(f"{'#':>3}  {'rating':>7}  {'mu':>6} {'rd':>5} {'M':>4}  player")
        for i, r in enumerate(rows[: opts["top"]], start=1):
            self.stdout.write(
                f"{i:>3}  {score(r):>7.1f}  {r.mu:>6.0f} {r.rd:>5.0f} "
                f"{r.matches_played:>4}  {r.player.name_display} ({r.player.country_code})"
            )
