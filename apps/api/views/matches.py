"""Single matches, a player's run through a tournament, and match records
(longest, most rallies, biggest comebacks)."""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import Match, MatchPlayer, MatchStatistics, RatingHistory

from ..serializers import MatchSerializer, PlayerBriefSerializer
from .common import _match_card


class PerformancePathView(APIView):
    """GET /api/performance/path?player=&event=&tournament= — the player's/pair's
    run through one tournament: each match's opponent, round, result, score, ELO
    change and time. Powers the "who did they beat" dropdown on performances."""

    def get(self, request):
        try:
            pid = int(request.query_params["player"])
            tid = int(request.query_params["tournament"])
        except (KeyError, ValueError):
            raise ValidationError({"detail": "player, event, tournament required"})
        event = request.query_params.get("event")

        mps = (
            MatchPlayer.objects.filter(
                player_id=pid, match__tournament_id=tid, match__event=event
            )
            .select_related("match")
            .prefetch_related("match__lineup__player", "match__games")
            .order_by("match__round_order", "match__match_id")
        )
        deltas = dict(
            RatingHistory.objects.filter(
                player_id=pid, match__tournament_id=tid, event=event
            ).values_list("match_id", "delta")
        )
        out = []
        for mp in mps:
            m = mp.match
            lineup = list(m.lineup.all())
            opp = [l.player for l in lineup if l.side != mp.side]
            partners = [
                l.player for l in lineup
                if l.side == mp.side and l.player_id != pid
            ]
            games = [
                (g.side1_points, g.side2_points)
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            if mp.side == 2:
                games = [(b, a) for a, b in games]
            d = deltas.get(m.match_id)
            out.append({
                "match_id": m.match_id,
                "round_name": m.round_name,
                "round_order": m.round_order,
                "won": m.winner_side == mp.side,
                "match_time_utc": m.match_time_utc,
                "score": games,
                "score_status": m.score_status,
                "partners": PlayerBriefSerializer(partners, many=True).data,
                "opponents": PlayerBriefSerializer(opp, many=True).data,
                "elo_delta": round(d, 1) if d is not None else None,
            })
        return Response({"matches": out})


RECORD_KINDS = {
    # kind: (stats field, order, only Normal matches)
    "longest": ("duration_min", "-duration_min", True),
    "rallies": ("team1_rallies_played", "-team1_rallies_played", True),
    "comebacks": ("max_comeback", "-max_comeback", True),
}


class RecordsView(APIView):
    """GET /api/records/{longest|rallies|comebacks}?event=&limit= — leaderboards
    of extreme matches, computed from the rally-by-rally match statistics.

    - longest   : most minutes on court
    - rallies   : most total rallies played
    - comebacks : biggest points deficit a side clawed back to win a game
    """

    def get(self, request, kind):
        if kind not in RECORD_KINDS:
            raise ValidationError({"detail": f"unknown record kind '{kind}'"})
        field, order, normal_only = RECORD_KINDS[kind]
        event = request.query_params.get("event")
        try:
            limit = min(int(request.query_params.get("limit", 25)), 100)
        except ValueError:
            limit = 25

        qs = (
            MatchStatistics.objects.exclude(**{field: None})
            .exclude(**{field: 0})
            .select_related("match__tournament")
            .prefetch_related("match__lineup__player", "match__games")
        )
        if normal_only:
            qs = qs.filter(match__score_status="Normal")
        if kind == "longest":
            # BWF's longest ever was ~161 min; anything past 200 is bad data.
            qs = qs.filter(duration_min__lte=200)
        if event:
            qs = qs.filter(match__event=event)
        qs = qs.order_by(order)[:limit]

        out = []
        for st in qs:
            card = _match_card(st.match)
            card["value"] = getattr(st, field)
            card["duration_min"] = st.duration_min
            card["rallies"] = st.total_rallies
            card["max_comeback"] = st.max_comeback
            out.append(card)
        return Response({"kind": kind, "event": event, "results": out})


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/matches/{id} — one match with lineup and games.
    GET /api/matches/{id}/statistics — rally stats + point progression
    (stored; the first request queues a background fetch and says "pending")."""

    queryset = (
        Match.objects.all()
        .select_related("tournament")
        .prefetch_related("lineup__player", "games")
    )
    serializer_class = MatchSerializer
    lookup_field = "match_id"

    @action(detail=True, methods=["get"])
    def statistics(self, request, match_id=None):
        """Stored rally stats, or {"available": false, "pending": true} while a
        background fetch runs (never calls BWF inside the request)."""
        from apps.ingest import statsjobs
        from apps.ingest.models import MatchStatistics

        from ..serializers import MatchStatisticsSerializer

        match = self.get_object()
        stats = MatchStatistics.objects.filter(match=match).first()
        if stats is not None:
            data = MatchStatisticsSerializer(stats).data
            data["available"] = True
            return Response(data)
        if not match.code:
            return Response({"available": False})
        status = statsjobs.enqueue(match)
        if status in (statsjobs.PENDING, statsjobs.RUNNING):
            statsjobs.kick()
            return Response({"available": False, "pending": True})
        return Response({"available": False})
