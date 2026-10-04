"""Home page composite payload and the discipline list."""
from __future__ import annotations

from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import PlayerRating, Tournament

from .common import DOUBLES, EVENTS, _subcall

# The "latest major" Home and Head-to-Head open on: newest completed one.
MAJOR_TIERS = (
    "Grade 1 – Individual Tournaments", "HSBC BWF World Tour Finals",
    "HSBC BWF World Tour Super 1000", "HSBC BWF World Tour Super 750",
)


class HomeView(APIView):
    """GET /api/home — everything the Home page shows, in one (cached) payload.

    Each key is exactly what the matching endpoint returns:
      events       /events
      tournaments  /tournaments?limit=12   (also the count and "this week")
      calibration  /analytics/calibration?event=ALL
      major        /tournaments/{latest completed major}  (or null)
      no1s         {event: /leaderboard or /pairs ?limit=2&min_matches=5}
      board        /leaderboard?event=MS&limit=6&min_matches=5
      upsets       /analytics/upsets?limit=3&min_matches=3
    """

    def get(self, request):
        latest_major = (
            Tournament.objects.filter(
                match_count__gt=0, category_name__in=MAJOR_TIERS,
                end_date__lte=timezone.now().date(),
            ).order_by("-end_date").values_list("tournament_id", flat=True).first()
        )
        no1s = {
            e: _subcall(request, "/api/pairs" if e in DOUBLES else "/api/leaderboard",
                        event=e, limit=2, min_matches=5)
            for e in EVENTS
        }
        return Response({
            "events": _subcall(request, "/api/events"),
            "tournaments": _subcall(request, "/api/tournaments", limit=12),
            "calibration": _subcall(request, "/api/analytics/calibration", event="ALL"),
            "major": _subcall(request, f"/api/tournaments/{latest_major}") if latest_major else None,
            "no1s": no1s,
            "board": _subcall(request, "/api/leaderboard", event="MS", limit=6, min_matches=5),
            "upsets": _subcall(request, "/api/analytics/upsets", limit=3, min_matches=3),
        })


class EventsView(APIView):
    """GET /api/events — the discipline buckets and their rated-player counts."""

    def get(self, request):
        counts = dict(
            PlayerRating.objects.filter(event__in=EVENTS).order_by()
            .values_list("event").annotate(n=Count("id"))
        )
        return Response(
            [{"event": e, "rated_players": counts.get(e, 0)} for e in EVENTS]
        )
