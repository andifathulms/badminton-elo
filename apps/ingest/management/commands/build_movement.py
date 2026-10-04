"""Store each player's board rank now and MOVEMENT_DAYS ago, for rank arrows.

Run after `rate` (which recreates PlayerRating rows). For every discipline the
default CURRENT board is: >= MIN_MATCHES rated matches, active within
ACTIVE_DAYS, ranked by the conservative rating mu − 2·rd. The same board is
rebuilt as it stood at `cutoff = latest data − MOVEMENT_DAYS`:

  * a player's state at the cutoff is the `mu_before`/`rd_before` of their first
    rating-history row after it (ratings are tournament-locked, so that is the
    state carried into the next period); with no later rows it is today's state;
  * matches at the cutoff = matches_played − rows after it;
  * active at the cutoff = their last row on or before it is within ACTIVE_DAYS.

Ranks are also computed within gender (the split XD boards). Deterministic.
"""
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Max

from apps.ingest.boards import ACTIVE_DAYS, BOARD_MIN_MATCHES as MIN_MATCHES, board_ranks
from apps.ingest.management.base import DataCommand
from apps.ingest.models import PlayerRating, RatingHistory

MOVEMENT_DAYS = 28


class Command(DataCommand):
    help = "Compute current and 4-weeks-ago board ranks for rank-movement arrows."

    def handle(self, *args, **opts):
        latest = PlayerRating.objects.aggregate(m=Max("last_match_utc"))["m"]
        if latest is None:
            self.stdout.write("no ratings; nothing to do.")
            return
        now_cut = latest - timedelta(days=ACTIVE_DAYS)
        cutoff = latest - timedelta(days=MOVEMENT_DAYS)
        prev_active = cutoff - timedelta(days=ACTIVE_DAYS)

        # order_by() clears the model ordering (event, -mu), or distinct() is per row.
        events = sorted(PlayerRating.objects.order_by().values_list("event", flat=True).distinct())
        updated = []
        for event in events:
            ratings = list(
                PlayerRating.objects.filter(event=event).select_related("player")
                .only("id", "player_id", "mu", "rd", "matches_played", "last_match_utc", "player__gender")
            )
            # First row after the cutoff (state carried in) + count of later rows.
            after = {}
            later = defaultdict(int)
            for pid, mu_b, rd_b in (
                RatingHistory.objects.filter(event=event, applied_utc__gt=cutoff)
                .order_by("applied_utc", "match_id")
                .values_list("player_id", "mu_before", "rd_before")
            ):
                after.setdefault(pid, (mu_b, rd_b))
                later[pid] += 1
            last_before = dict(
                RatingHistory.objects.filter(event=event, applied_utc__lte=cutoff, player_id__in=list(after))
                .values("player_id").annotate(m=Max("applied_utc")).values_list("player_id", "m")
            )

            now_rows, prev_rows = [], []
            for r in ratings:
                g = r.player.gender or ""
                if r.matches_played >= MIN_MATCHES and r.last_match_utc and r.last_match_utc >= now_cut:
                    now_rows.append((r.player_id, g, r.mu - 2.0 * r.rd))
                if r.player_id in after:
                    mu, rd = after[r.player_id]
                    last = last_before.get(r.player_id)
                    n = r.matches_played - later[r.player_id]
                else:
                    mu, rd, last, n = r.mu, r.rd, r.last_match_utc, r.matches_played
                if n >= MIN_MATCHES and last and last >= prev_active:
                    prev_rows.append((r.player_id, g, mu - 2.0 * rd))

            rank_now, g_now = board_ranks(now_rows)
            rank_prev, g_prev = board_ranks(prev_rows)

            for r in ratings:
                r.rank = rank_now.get(r.player_id)
                r.rank_prev = rank_prev.get(r.player_id)
                r.rank_gender = g_now.get(r.player_id)
                r.rank_prev_gender = g_prev.get(r.player_id)
                updated.append(r)
            moved = sum(1 for r in ratings if r.rank and r.rank_prev and r.rank != r.rank_prev)
            self.stdout.write(f"{event}: {len(rank_now)} ranked now, {len(rank_prev)} at {cutoff:%Y-%m-%d}, {moved} moved")

        with transaction.atomic():
            PlayerRating.objects.bulk_update(
                updated, ["rank", "rank_prev", "rank_gender", "rank_prev_gender"], batch_size=2000
            )
        self.stdout.write(f"movement built (vs {MOVEMENT_DAYS} days before {latest:%Y-%m-%d}).")
