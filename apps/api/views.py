"""DRF read-only views (PRD §12).

    GET /api/leaderboard?event=XD[&min_matches=5&order=rating|mu]
    GET /api/players/{id}
    GET /api/players/{id}/history?event=XD
    GET /api/matches/{id}
    GET /api/events
"""
from __future__ import annotations

from django.db.models import DateTimeField, F, FloatField
from django.db.models.functions import Cast, Coalesce
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count

from apps.ingest.models import (
    Draw,
    Match,
    MatchPlayer,
    Partnership,
    Player,
    PlayerRating,
    RatingHistory,
    Tournament,
)

from .serializers import (
    DrawBriefSerializer,
    LeaderboardEntrySerializer,
    MatchListSerializer,
    MatchSerializer,
    PairSerializer,
    PlayerBriefSerializer,
    PlayerDetailSerializer,
    PlayerMatchSerializer,
    RatingHistoryPointSerializer,
    TournamentListSerializer,
)

EVENTS = ("MS", "WS", "MD", "WD", "XD")
DOUBLES = ("MD", "WD", "XD")


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
        # XD holds both men and women — split the individual board by gender.
        gender = self.request.query_params.get("gender")
        if gender in ("M", "F"):
            qs = qs.filter(player__gender=gender)
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
    """GET /api/players/{id} — player detail; GET /api/players?q=lin — search."""

    queryset = Player.objects.all().prefetch_related("ratings")
    lookup_field = "player_id"

    def get_serializer_class(self):
        return (
            PlayerBriefSerializer if self.action == "list" else PlayerDetailSerializer
        )

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name_display__icontains=q).order_by("name_display")
        return qs

    @action(detail=True, methods=["get"])
    def history(self, request, player_id=None):
        """Rating-over-time points for the player (optionally one --event)."""
        qs = RatingHistory.objects.filter(player_id=player_id).order_by("applied_utc")
        event = request.query_params.get("event")
        if event:
            qs = qs.filter(event=event)
        return Response(RatingHistoryPointSerializer(qs, many=True).data)


class PairsView(generics.ListAPIView):
    """GET /api/pairs?event=MD[&min_matches=5] — doubles/mixed partnerships
    ranked by combined strength (conservative), with their record together."""

    serializer_class = PairSerializer

    def get_queryset(self):
        event = self.request.query_params.get("event")
        if event not in DOUBLES:
            raise ValidationError({"event": f"required; one of {', '.join(DOUBLES)}"})
        try:
            min_matches = int(self.request.query_params.get("min_matches", 5))
        except ValueError:
            raise ValidationError({"min_matches": "must be an integer"})
        qs = Partnership.objects.filter(
            event=event, matches_together__gte=min_matches
        ).select_related("player1", "player2")
        if self.request.query_params.get("ranking") == "peak":
            return qs.exclude(combined_peak_mu=None).order_by("-combined_peak_mu")
        return qs.annotate(
            _rating=F("combined_mu") - 2.0 * F("combined_rd")
        ).order_by("-_rating")


class PlayerMatchesView(generics.ListAPIView):
    """GET /api/players/{id}/matches[?event=] — the player's match history with
    the ELO gained/lost in each (most recent first, paginated)."""

    serializer_class = PlayerMatchSerializer

    def get_queryset(self):
        # Many historical matches lack match_time_utc; fall back to the
        # tournament date so the sort is reliably most-recent-first.
        qs = (
            MatchPlayer.objects.filter(player_id=self.kwargs["player_id"])
            .select_related("match", "match__tournament")
            .prefetch_related("match__lineup__player", "match__games")
            .annotate(
                _when=Coalesce(
                    "match__match_time_utc",
                    "match__tournament__start_date",
                    output_field=DateTimeField(),
                )
            )
            .order_by(F("_when").desc(nulls_last=True), "-match__match_id")
        )
        event = self.request.query_params.get("event")
        return qs.filter(match__event=event) if event else qs

    def list(self, request, *args, **kwargs):
        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        pid = int(self.kwargs["player_id"])
        deltas = dict(
            RatingHistory.objects.filter(
                player_id=pid, match_id__in=[mp.match_id for mp in rows]
            ).values_list("match_id", "delta")
        )
        deltas = {mid: round(d, 1) for mid, d in deltas.items()}
        data = self.get_serializer(rows, many=True, context={"deltas": deltas}).data
        return self.get_paginated_response(data)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/matches/{id} — one match with lineup and games.
    GET /api/matches/{id}/statistics — rally stats + point progression
    (served from cache, fetched live from BWF on first request)."""

    queryset = (
        Match.objects.all()
        .select_related("tournament")
        .prefetch_related("lineup__player", "games")
    )
    serializer_class = MatchSerializer
    lookup_field = "match_id"

    @action(detail=True, methods=["get"])
    def statistics(self, request, match_id=None):
        from apps.ingest.h2h import fetch_and_store_stats
        from apps.ingest.models import MatchStatistics

        from .serializers import MatchStatisticsSerializer

        match = self.get_object()
        stats = MatchStatistics.objects.filter(match=match).first()
        if stats is None:
            try:
                stats = fetch_and_store_stats(match)
            except Exception:  # noqa: BLE001 - live fetch is best-effort
                stats = None
        if stats is None:
            return Response({"available": False})
        data = MatchStatisticsSerializer(stats).data
        data["available"] = True
        return Response(data)


class TournamentViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/tournaments[?year=&q=] — list; GET /api/tournaments/{id} — detail
    with its draws and the finals (champions)."""

    lookup_field = "tournament_id"
    serializer_class = TournamentListSerializer

    def get_queryset(self):
        qs = (
            Tournament.objects.annotate(match_count=Count("matches"))
            .filter(match_count__gt=0)
            .order_by("-start_date")
        )
        year = self.request.query_params.get("year")
        if year and year.isdigit():
            qs = qs.filter(start_date__year=int(year))
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    @action(detail=True, methods=["get"])
    def matches(self, request, tournament_id=None):
        """GET /api/tournaments/{id}/matches[?event=] — bracket-ordered matches."""
        qs = (
            Match.objects.filter(tournament_id=tournament_id)
            .prefetch_related("lineup__player", "games")
            .order_by("event", "round_order", "match_id")
        )
        event = request.query_params.get("event")
        if event:
            qs = qs.filter(event=event)
        page = self.paginate_queryset(qs)
        data = MatchListSerializer(page, many=True).data
        return self.get_paginated_response(data)

    def retrieve(self, request, *args, **kwargs):
        t = self.get_object()
        draws = Draw.objects.filter(tournament=t).order_by("event", "stage")
        events = list(
            Match.objects.filter(tournament=t)
            .values("event")
            .annotate(n=Count("match_id"))
            .order_by("-n")
        )
        finals = (
            Match.objects.filter(tournament=t, round_name__in=("Final", "F"))
            .select_related("tournament")
            .prefetch_related("lineup__player")
        )
        return Response(
            {
                **TournamentListSerializer(
                    Tournament.objects.annotate(match_count=Count("matches")).get(
                        pk=t.pk
                    )
                ).data,
                "slug": t.slug,
                "draws": DrawBriefSerializer(draws, many=True).data,
                "events": events,
                "finals": [
                    {
                        "match_id": m.match_id,
                        "event": m.event,
                        "winner_side": m.winner_side,
                        "champions": PlayerBriefSerializer(
                            [l.player for l in m.lineup.all() if l.side == m.winner_side],
                            many=True,
                        ).data,
                    }
                    for m in finals
                ],
            }
        )


class EventsView(APIView):
    """GET /api/events — the discipline buckets and their rated-player counts."""

    def get(self, request):
        counts = {
            e: PlayerRating.objects.filter(event=e).count() for e in EVENTS
        }
        return Response(
            [{"event": e, "rated_players": counts[e]} for e in EVENTS]
        )
