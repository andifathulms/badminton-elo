"""DRF read-only views (PRD §12).

    GET /api/leaderboard?event=XD[&min_matches=5&order=rating|mu]
    GET /api/players/{id}
    GET /api/players/{id}/history?event=XD
    GET /api/matches/{id}
    GET /api/events
"""
from __future__ import annotations

from django.db.models import F, FloatField
from django.db.models.functions import Cast
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import Match, Player, PlayerRating, RatingHistory

from .serializers import (
    LeaderboardEntrySerializer,
    MatchSerializer,
    PlayerDetailSerializer,
    RatingHistoryPointSerializer,
)

EVENTS = ("MS", "WS", "MD", "WD", "XD")


class LeaderboardView(generics.ListAPIView):
    """Paginated ranking for one discipline.

    ?ranking=current (default) ranks live form by the conservative mu − 2·rd;
    ?ranking=peak ranks by the all-time peak mu (best a player ever was), which
    surfaces retired greats (Lin Dan, Lee Chong Wei) that the current board
    understates. ?order=mu ranks current by raw skill instead.
    """

    serializer_class = LeaderboardEntrySerializer

    def get_queryset(self):
        event = self.request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError(
                {"event": f"required; one of {', '.join(EVENTS)}"}
            )
        try:
            min_matches = int(self.request.query_params.get("min_matches", 5))
        except ValueError:
            raise ValidationError({"min_matches": "must be an integer"})

        qs = (
            PlayerRating.objects.filter(event=event, matches_played__gte=min_matches)
            .select_related("player")
        )
        ranking = self.request.query_params.get("ranking", "current")
        if ranking == "peak":
            return qs.exclude(peak_mu=None).order_by("-peak_mu")

        order = self.request.query_params.get("order", "rating")
        if order == "mu":
            return qs.order_by("-mu", "rd")
        # conservative rating = mu - 2*rd, ranked DB-side
        return qs.annotate(
            _rating=Cast(F("mu") - 2.0 * F("rd"), FloatField())
        ).order_by("-_rating")


class PlayerViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/players/{id} — player with ratings across disciplines."""

    queryset = Player.objects.all().prefetch_related("ratings")
    serializer_class = PlayerDetailSerializer
    lookup_field = "player_id"

    @action(detail=True, methods=["get"])
    def history(self, request, player_id=None):
        """Rating-over-time points for the player (optionally one --event)."""
        qs = RatingHistory.objects.filter(player_id=player_id).order_by("applied_utc")
        event = request.query_params.get("event")
        if event:
            qs = qs.filter(event=event)
        return Response(RatingHistoryPointSerializer(qs, many=True).data)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/matches/{id} — one match with lineup and games."""

    queryset = (
        Match.objects.all()
        .select_related("tournament")
        .prefetch_related("lineup__player", "games")
    )
    serializer_class = MatchSerializer
    lookup_field = "match_id"


class EventsView(APIView):
    """GET /api/events — the discipline buckets and their rated-player counts."""

    def get(self, request):
        counts = {
            e: PlayerRating.objects.filter(event=e).count() for e in EVENTS
        }
        return Response(
            [{"event": e, "rated_players": counts[e]} for e in EVENTS]
        )
