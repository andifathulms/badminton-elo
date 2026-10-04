"""Player profile, search, rating history, playing style and match history."""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Avg, Count, DateTimeField, F
from django.db.models.functions import Coalesce, Round
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.ingest.models import MatchPlayer, MatchStatistics, Player, RatingHistory

from ..serializers import (
    PlayerBriefSerializer,
    PlayerDetailSerializer,
    PlayerMatchSerializer,
    RatingHistoryPointSerializer,
)


def history_points(player_id, event=None, resolution=None) -> list:
    """Rating-over-time points for a player (optionally one discipline).

    resolution="tournament" gives one point per rating period instead of one
    per match — exact, because ratings only change once per tournament (the
    engine is tournament-locked), and much smaller.
    """
    qs = RatingHistory.objects.filter(player_id=player_id).order_by(
        "applied_utc", "match_id"
    )
    if event:
        qs = qs.filter(event=event)
    if resolution != "tournament":
        return RatingHistoryPointSerializer(qs, many=True).data

    periods: dict = {}  # (event, tournament) -> point, in first-seen order
    for row in qs.values(
        "event", "match_id", "mu_before", "mu_after", "rd_before", "rd_after",
        "delta", "applied_utc", "match__tournament_id", "match__tournament__name",
    ):
        key = (row["event"], row["match__tournament_id"])
        p = periods.get(key)
        if p is None:
            periods[key] = p = {
                "event": row["event"],
                "tournament": {"id": row["match__tournament_id"],
                               "name": row["match__tournament__name"]},
                "mu_before": row["mu_before"], "rd_before": row["rd_before"],
                "delta": 0.0, "matches": 0,
            }
        p["delta"] += row["delta"]
        p["matches"] += 1
        p.update(match=row["match_id"], mu_after=row["mu_after"],
                 rd_after=row["rd_after"], applied_utc=row["applied_utc"])
    for p in periods.values():
        for k in ("mu_before", "rd_before", "mu_after", "rd_after", "delta"):
            p[k] = round(p[k], 1)
    return list(periods.values())


class PlayerViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/players/{id} — player detail; GET /api/players?q=lin — search;
    GET /api/players?ids=1,2,3 — those players (brief, unpaginated, in order)."""

    queryset = Player.objects.all()
    lookup_field = "player_id"

    def get_serializer_class(self):
        return (
            PlayerBriefSerializer if self.action == "list" else PlayerDetailSerializer
        )

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action != "list":
            return qs.prefetch_related("ratings")
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name_display__icontains=q).order_by("name_display")
        return qs

    def list(self, request, *args, **kwargs):
        raw = request.query_params.get("ids")
        if raw is None:
            return super().list(request, *args, **kwargs)
        try:
            ids = [int(x) for x in raw.split(",") if x][:20]
        except ValueError:
            raise ValidationError({"ids": "comma-separated player ids"})
        found = {p.player_id: p for p in Player.objects.filter(player_id__in=ids)}
        return Response(PlayerBriefSerializer(
            [found[i] for i in ids if i in found], many=True
        ).data)

    def retrieve(self, request, *args, **kwargs):
        """Player detail. ?include=history embeds the rating history (tournament
        resolution) of the discipline the profile opens on — the one they're
        ranked best in, else their strongest — so the page needs no second
        round-trip before drawing the chart."""
        player = self.get_object()
        data = self.get_serializer(player).data
        if "history" in request.query_params.get("include", "").split(","):
            ratings = data["ratings"]  # ordered by -mu
            ranked = sorted((r for r in ratings if r.get("rank")), key=lambda r: r["rank"])
            event = (ranked[0] if ranked else ratings[0])["event"] if ratings else None
            data["history_event"] = event
            data["history"] = (
                history_points(player.player_id, event, "tournament") if event else []
            )
        return Response(data)

    @action(detail=True, methods=["get"])
    def history(self, request, player_id=None):
        """Rating-over-time points (?event=, ?resolution=tournament)."""
        return Response(history_points(
            player_id,
            request.query_params.get("event"),
            request.query_params.get("resolution"),
        ))

    @action(detail=True, methods=["get"])
    def style(self, request, player_id=None):
        """Playing style: avg rallies per match & avg match duration, per
        discipline. With ?partner=<id>, restrict to matches played as that
        pair (both on the same side)."""
        partner = request.query_params.get("partner")
        if partner:
            # matches where this player and the partner are on the same side
            sides = defaultdict(dict)  # match_id -> {player_id: side}
            for mp in MatchPlayer.objects.filter(
                player_id__in=[player_id, partner]
            ).values("match_id", "player_id", "side"):
                sides[mp["match_id"]][mp["player_id"]] = mp["side"]
            pid, par = int(player_id), int(partner)
            match_ids = [
                mid for mid, s in sides.items()
                if s.get(pid) is not None and s.get(pid) == s.get(par)
            ]
            style = _style_by_event({"match_id__in": match_ids})
        else:
            style = _style_by_event({"match__lineup__player_id": player_id})
        return Response({"style": style})


def _style_by_event(match_filter):
    """Average rally count & match duration per discipline for a set of matches
    (identified by `match_filter`, a dict of MatchStatistics lookups). Only
    Normal matches with real stats contribute."""
    rows = (
        MatchStatistics.objects.filter(
            match__score_status="Normal", **match_filter
        )
        .exclude(duration_min=None)
        .values("match__event")
        .annotate(
            matches=Count("match_id"),
            avg_duration=Round(Avg("duration_min"), 1),
            avg_rallies=Round(Avg("team1_rallies_played"), 1),
        )
        .order_by("match__event")
    )
    return [
        {
            "event": r["match__event"],
            "matches": r["matches"],
            "avg_duration": r["avg_duration"],
            "avg_rallies": r["avg_rallies"],
        }
        for r in rows
    ]


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
        from ..elo import chained_elo

        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        pid = int(self.kwargs["player_id"])
        # Chain before/after within each tournament so a run reads cumulatively
        # — one query for every tournament on the page.
        tour_ids = {mp.match.tournament_id for mp in rows if mp.match.tournament_id}
        chains = chained_elo(tour_ids, [pid])
        deltas = {
            mid: {"before": round(b), "after": round(a), "delta": round(d, 1)}
            for mid, by_player in chains.items()
            for (b, a, d) in [by_player[pid]]
        }
        data = self.get_serializer(rows, many=True, context={"deltas": deltas}).data
        return self.get_paginated_response(data)
