"""Tournament list, the by-year master view, tiers, detail, bracket matches
and team-cup ties."""
from __future__ import annotations

from datetime import date

from django.db.models import Count
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ingest.models import Draw, Match, Tournament, TournamentPerformance

from ..serializers import (
    DrawBriefSerializer,
    MatchListSerializer,
    PlayerBriefSerializer,
    TournamentListSerializer,
)
from .common import _PRESTIGE_RANK, prestige_group, team_cup_kind


class TournamentViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/tournaments[?year=&q=] — list; GET /api/tournaments/{id} — detail
    with its draws and the finals (champions)."""

    lookup_field = "tournament_id"
    serializer_class = TournamentListSerializer

    def get_queryset(self):
        qs = Tournament.objects.filter(match_count__gt=0).order_by("-start_date")
        year = self.request.query_params.get("year")
        if year and year.isdigit():
            qs = qs.filter(start_date__year=int(year))
        tier = self.request.query_params.get("tier")
        if tier:
            qs = qs.filter(category_name=tier)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    # Prestige order for the tier filter; anything unlisted sorts after, A–Z.
    TIER_ORDER = [
        "HSBC BWF World Tour Finals",
        "HSBC BWF World Tour Super 1000",
        "HSBC BWF World Tour Super 750",
        "HSBC BWF World Tour Super 500",
        "HSBC BWF World Tour Super 300",
        "BWF Tour Super 100",
        "World Superseries Premier",
        "World Superseries",
        "Grand Prix Gold",
        "Grand Prix",
        "Continental Individual Championships",
        "Continental Team Championships",
        "International Challenge",
        "International Series",
        "Future Series",
    ]

    @action(detail=False)
    def master(self, request):
        """GET /api/tournaments/master?year=Y — every tournament that year,
        sorted by prestige (multi-sport & championships on top), each tagged
        with its section group. Powers the by-year 'tournament master' view."""
        year = request.query_params.get("year")
        qs = Tournament.objects.all()
        if year and year.isdigit():
            qs = qs.filter(start_date__year=int(year))
        tours = sorted(
            qs, key=lambda t: (_PRESTIGE_RANK.get(t.category_name, 999),
                               t.start_date or date(1900, 1, 1), t.name))
        data = TournamentListSerializer(tours, many=True).data
        for row, t in zip(data, tours):
            row["group"] = prestige_group(t.category_name or "")
        return Response({"year": year, "count": len(data), "results": data})

    @action(detail=False)
    def tiers(self, request):
        """Distinct non-empty tiers present, ordered by prestige then count."""
        rows = (
            Tournament.objects.filter(match_count__gt=0)
            .exclude(category_name="")
            .exclude(category_name=None)
            .values("category_name")
            .annotate(n=Count("tournament_id", distinct=True))
        )
        rank = {name: i for i, name in enumerate(self.TIER_ORDER)}
        ordered = sorted(
            rows, key=lambda r: (rank.get(r["category_name"], 999), r["category_name"])
        )
        return Response(
            [{"tier": r["category_name"], "count": r["n"]} for r in ordered]
        )

    @action(detail=True, methods=["get"])
    def matches(self, request, tournament_id=None):
        """GET /api/tournaments/{id}/matches[?event=&round=] — bracket-ordered.

        With ?round= present the response also lists the event's rounds
        (`rounds`: name, order, count) and holds only the asked rounds'
        matches (comma-separated, e.g. QF,SF,F); an empty or unknown value
        picks the earliest round (`round` says what was served). The page
        loads one round at a time instead of the whole draw.
        """
        qs = (
            Match.objects.filter(tournament_id=tournament_id)
            .prefetch_related("lineup__player", "games")
            .order_by("event", "round_order", "match_id")
        )
        event = request.query_params.get("event")
        if event:
            qs = qs.filter(event=event)
        by_round = "round" in request.query_params
        rounds, chosen = [], None
        if by_round:
            rounds = [
                {"round_name": r["round_name"], "round_order": r["round_order"], "count": r["n"]}
                for r in qs.order_by().values("round_name", "round_order")
                .annotate(n=Count("match_id")).order_by("round_order", "round_name")
            ]
            names = [r["round_name"] for r in rounds]
            asked = [r for r in request.query_params.get("round", "").split(",") if r]
            valid = [r for r in asked if r in names] or names[:1]
            chosen = ",".join(valid) or None
            qs = qs.filter(round_name__in=valid)
        page = self.paginate_queryset(qs)
        data = MatchListSerializer(page, many=True).data
        # Attach each side's ELO for the match (pair mean for doubles), chained
        # across the tournament so the running figures read correctly.
        from ..elo import chained_elo

        # Only the players on this page (their chains still span the whole run).
        on_page = {l.player_id for m in page for l in m.lineup.all()}
        elo_map = chained_elo([int(tournament_id)], on_page)
        for m, row in zip(page, data):
            pm = elo_map.get(m.match_id, {})
            team = {}
            for side in (1, 2):
                vals = [
                    pm[l.player_id]
                    for l in m.lineup.all()
                    if l.side == side and l.player_id in pm
                ]
                if vals:
                    team[side] = {
                        "before": round(sum(v[0] for v in vals) / len(vals)),
                        "after": round(sum(v[1] for v in vals) / len(vals)),
                        "delta": round(sum(v[2] for v in vals) / len(vals), 1),
                    }
            row["team_elo"] = team
        response = self.get_paginated_response(data)
        if by_round:
            response.data["rounds"] = rounds
            response.data["round"] = chosen
        return response

    @action(detail=True, methods=["get"])
    def ties(self, request, tournament_id=None):
        """GET /api/tournaments/{id}/ties — a team cup as nation-vs-nation ties
        (precomputed by `build_ties`; see apps/api/ties.py)."""
        from apps.ingest.models import TournamentTies

        from ..ties import build_ties

        stored = TournamentTies.objects.filter(tournament_id=tournament_id).first()
        if stored is not None:
            return Response(stored.payload)
        return Response(build_ties(self.get_object()))

    def _movers(self, t):
        """Top-3 ELO gainers and losers per discipline at this tournament.

        Uses TournamentPerformance (net_delta per player/event), collapsing the
        two members of a doubles pair into one entry.
        """
        tps = (
            TournamentPerformance.objects.filter(tournament=t)
            .select_related("player", "partner")
            .order_by("event", "-net_delta")
        )
        by_event: dict = {}
        for tp in tps:
            by_event.setdefault(tp.event, []).append(tp)

        def row(tp):
            return {
                "player": PlayerBriefSerializer(tp.player).data,
                "partner": PlayerBriefSerializer(tp.partner).data if tp.partner_id else None,
                "net_delta": round(tp.net_delta, 1),
                "mu_start": round(tp.mu_start),
                "mu_end": round(tp.mu_end),
            }

        out = {}
        for event, rows in by_event.items():
            seen: set = set()
            uniq = []
            for tp in rows:
                if tp.partner_id:
                    key = frozenset((tp.player_id, tp.partner_id))
                    if key in seen:
                        continue
                    seen.add(key)
                uniq.append(tp)
            gainers = [row(tp) for tp in uniq[:3] if tp.net_delta > 0]
            losers = [row(tp) for tp in uniq[::-1][:3] if tp.net_delta < 0]
            if gainers or losers:
                out[event] = {"gainers": gainers, "losers": losers}
        return out

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
                **TournamentListSerializer(t).data,
                "slug": t.slug,
                "is_team_cup": team_cup_kind(t) is not None,
                "cup": team_cup_kind(t),
                "draws": DrawBriefSerializer(draws, many=True).data,
                "events": events,
                "movers": self._movers(t),
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
