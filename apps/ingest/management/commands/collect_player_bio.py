"""Fill player bio (height, hand, residence, languages, birthplace, prize money)
from BWF's vue-player-bio endpoint.

Only BWF-id players have a bio (Wikipedia synthetic ids don't). Cache-first and
polite via BwfClient. Defaults to rated players (those shown in the app); widen
with --all or --min-matches.

    python manage.py collect_player_bio                 # rated players, missing bio
    python manage.py collect_player_bio --all --refetch  # everyone, re-fetch
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.models import Player, PlayerRating

BASE = 2_000_000_000


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# BWF hand codes: "1"=right, "2"=left; curated profiles already use R/L.
HAND = {"1": "R", "2": "L", "R": "R", "L": "L", "r": "R", "l": "L"}


class Command(BaseCommand):
    help = "Fill Player bio fields from BWF vue-player-bio."

    def add_arguments(self, p):
        p.add_argument("--all", action="store_true", help="all BWF players, not just rated")
        p.add_argument("--min-matches", type=int, default=0)
        p.add_argument("--refetch", action="store_true", help="also update players that already have bio")
        p.add_argument("--limit", type=int, default=0, help="cap this run")

    def handle(self, *args, **o):
        qs = Player.objects.filter(player_id__lt=BASE)
        if not o["all"]:
            rated = PlayerRating.objects.values_list("player_id", flat=True).distinct()
            qs = qs.filter(player_id__in=list(rated))
        if o["min_matches"]:
            qs = qs.filter(ratings__matches_played__gte=o["min_matches"]).distinct()
        if not o["refetch"]:
            qs = qs.filter(height_cm=None, current_residence="")
        ids = list(qs.values_list("player_id", flat=True))
        if o["limit"]:
            ids = ids[:o["limit"]]
        self.stdout.write(f"fetching bio for {len(ids)} players…")

        client = BwfClient()
        done = fail = 0
        try:
            for pid in ids:
                try:
                    raw = client.get_json(endpoints.vue_player_bio(pid))
                except Exception as e:
                    fail += 1
                    continue
                if not isinstance(raw, dict):
                    continue
                p = Player.objects.get(player_id=pid)
                h = _int(raw.get("height"))
                if h:
                    p.height_cm = h
                hand = HAND.get((raw.get("hand") or "").strip())
                if hand:
                    p.plays = hand
                p.current_residence = (raw.get("current_residence") or "")[:128]
                p.languages = (raw.get("languages") or "")[:128]
                p.prize_money = (str(raw.get("prize_money") or ""))[:32]
                qa = raw.get("qa") or {}
                p.birth_place = (qa.get("place_of_birth") or "")[:128]
                p.save(update_fields=["height_cm", "plays", "current_residence",
                                      "languages", "prize_money", "birth_place"])
                done += 1
                if done % 200 == 0:
                    self.stdout.write(f"  …{done} done")
        finally:
            client.close()
        self.stdout.write(self.style.SUCCESS(f"Filled {done} players ({fail} failed)."))
