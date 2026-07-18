"""DRF read-only views (PRD §12).

    GET /api/leaderboard?event=XD[&min_matches=5&order=rating|mu]
    GET /api/players/{id}
    GET /api/players/{id}/history?event=XD
    GET /api/matches/{id}
    GET /api/events
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, DateTimeField, F, FloatField, Max
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import (
    Draw,
    Match,
    MatchPlayer,
    Partnership,
    Player,
    PlayerRating,
    RatingHistory,
    Tournament,
    TournamentPerformance,
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
    TournamentPerformanceSerializer,
)

EVENTS = ("MS", "WS", "MD", "WD", "XD")
DOUBLES = ("MD", "WD", "XD")
ACTIVE_DAYS = 365  # a player/pair idle longer than this counts as retired

_active_cutoff_cache = {}


def active_cutoff():
    """Anything last active before this is 'retired' — excluded from CURRENT
    rankings (still counted in all-time/peak). Measured from the latest match in
    the data (data-relative), so the rule holds even if collection pauses."""
    latest = PlayerRating.objects.aggregate(m=Max("last_match_utc"))["m"]
    ref = latest or timezone.now()
    return ref - timedelta(days=ACTIVE_DAYS)


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

        # Current board: hide retired players (idle > 1 year) unless asked.
        if self.request.query_params.get("include_inactive") != "1":
            qs = qs.filter(last_match_utc__gte=active_cutoff())

        order = self.request.query_params.get("order", "rating")
        if order == "mu":
            return qs.order_by("-mu", "rd")
        # conservative rating = mu - 2*rd, ranked DB-side
        return qs.annotate(
            _rating=Cast(F("mu") - 2.0 * F("rd"), FloatField())
        ).order_by("-_rating")

    def list(self, request, *args, **kwargs):
        """Attach each page row's win% (batched over the page's players)."""
        from django.db.models import Case, F, IntegerField, Sum, When

        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        event = request.query_params.get("event")
        pids = [r.player_id for r in rows]
        recs = {
            r["player_id"]: r
            for r in MatchPlayer.objects.filter(
                player_id__in=pids, match__event=event
            )
            .values("player_id")
            .annotate(
                played=Count("id"),
                won=Sum(
                    Case(
                        When(side=F("match__winner_side"), then=1),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
            )
        }
        data = self.get_serializer(rows, many=True).data
        for row in data:
            r = recs.get(row["player"]["player_id"])
            if r and r["played"]:
                row["wins"] = r["won"] or 0
                row["losses"] = r["played"] - (r["won"] or 0)
                row["win_pct"] = round(100.0 * (r["won"] or 0) / r["played"], 1)
            else:
                row["wins"] = row["losses"] = 0
                row["win_pct"] = None
        return self.get_paginated_response(data)


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
        # Current pairs: hide partnerships that haven't played TOGETHER in a
        # year (even if one member is still active with a different partner).
        if self.request.query_params.get("include_inactive") != "1":
            qs = qs.filter(last_match_utc__gte=active_cutoff())
        return qs.annotate(
            _rating=F("combined_mu") - 2.0 * F("combined_rd")
        ).order_by("-_rating")


class PairDetailView(APIView):
    """GET /api/pairs/detail?event=&p1=&p2= — a partnership with its record and
    the matches the two players contested together."""

    def get(self, request):
        event = request.query_params.get("event")
        try:
            p1 = int(request.query_params["p1"])
            p2 = int(request.query_params["p2"])
        except (KeyError, ValueError):
            raise ValidationError({"detail": "event, p1, p2 required"})
        lo, hi = sorted((p1, p2))

        pair = (
            Partnership.objects.filter(event=event, player1_id=lo, player2_id=hi)
            .select_related("player1", "player2")
            .first()
        )

        # Matches where both players were on the SAME side.
        s1 = dict(
            MatchPlayer.objects.filter(player_id=lo, match__event=event).values_list(
                "match_id", "side"
            )
        )
        s2 = dict(
            MatchPlayer.objects.filter(player_id=hi, match__event=event).values_list(
                "match_id", "side"
            )
        )
        shared = [mid for mid, side in s1.items() if s2.get(mid) == side]
        matches = (
            Match.objects.filter(match_id__in=shared)
            .select_related("tournament")
            .prefetch_related("lineup__player", "games")
            .order_by("-match_time_utc", "-match_id")
        )
        # win/loss of the pair (they share a side).
        wins = sum(1 for m in matches if m.winner_side == s1.get(m.match_id))

        return Response(
            {
                "pair": PairSerializer(pair).data if pair else None,
                "player1": PlayerBriefSerializer(Player.objects.get(pk=lo)).data,
                "player2": PlayerBriefSerializer(Player.objects.get(pk=hi)).data,
                "event": event,
                "matches_together": len(shared),
                "wins": wins,
                "losses": len(shared) - wins,
                "matches": MatchListSerializer(matches, many=True).data,
            }
        )


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
        from .elo import cumulative_elo

        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        pid = int(self.kwargs["player_id"])
        # Chain before/after within each tournament so a run reads cumulatively.
        tour_ids = {mp.match.tournament_id for mp in rows if mp.match.tournament_id}
        cum: dict = {}
        for tid in tour_ids:
            cum.update(cumulative_elo(pid, tid))
        deltas = {
            mid: {"before": round(b), "after": round(a), "delta": round(d, 1)}
            for mid, (b, a, d) in cum.items()
        }
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
    def tiers(self, request):
        """Distinct non-empty tiers present, ordered by prestige then count."""
        rows = (
            Tournament.objects.annotate(mc=Count("matches"))
            .filter(mc__gt=0)
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
        # Attach each side's ELO for the match (pair mean for doubles), chained
        # across the tournament so the running figures read correctly.
        from .elo import tournament_match_elo

        elo_map = tournament_match_elo(int(tournament_id))
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
        return self.get_paginated_response(data)

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
                **TournamentListSerializer(
                    Tournament.objects.annotate(match_count=Count("matches")).get(
                        pk=t.pk
                    )
                ).data,
                "slug": t.slug,
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


class AnalyticsView(APIView):
    """GET /api/analytics/{tournament-gains|upsets}[?event=&min_matches=&limit=].

    tournament-gains: biggest net ELO gained across a single tournament.
    upsets: biggest single-match ELO gains (the standout wins).
    Doubles rows are collapsed into one pair (both partners) instead of two.
    """

    def get(self, request, kind):
        event = request.query_params.get("event")
        try:
            min_matches = int(request.query_params.get("min_matches", 2))
        except ValueError:
            min_matches = 2
        try:
            limit = min(int(request.query_params.get("limit", 40)), 100)
        except ValueError:
            limit = 40

        qs = TournamentPerformance.objects.select_related(
            "player", "partner", "tournament"
        ).filter(matches__gte=min_matches)
        if event in EVENTS:
            qs = qs.filter(event=event)
        if request.query_params.get("include_new") != "1":
            qs = qs.filter(rd_start__lte=130)
        if kind == "performances":
            qs = qs.exclude(perf_rating=None).order_by("-perf_rating")
        elif kind == "upsets":
            qs = qs.order_by("-best_delta")
        else:
            qs = qs.order_by("-net_delta")

        # Collapse the two members of a doubles pair into one row.
        seen: set = set()
        picked: list = []
        for tp in qs[:2000]:
            if len(picked) >= limit:
                break
            if tp.partner_id:
                key = (tp.tournament_id, tp.event, frozenset((tp.player_id, tp.partner_id)))
                if key in seen:
                    continue
                seen.add(key)
            picked.append(tp)

        rows = TournamentPerformanceSerializer(picked, many=True).data
        self._enrich_achievement(picked, rows)
        if kind == "upsets":
            self._enrich_upsets(picked, rows)
        return Response({"results": rows})

    def _enrich_achievement(self, picked, rows):
        """Tag each row with how far the player went (Champion/Runner-up/SF/…)."""
        from django.db.models import Q

        q = Q()
        for tp in picked:
            q |= Q(
                player_id=tp.player_id,
                match__tournament_id=tp.tournament_id,
                match__event=tp.event,
            )
        best: dict = {}
        if picked:
            for mp in MatchPlayer.objects.filter(q).select_related("match"):
                key = (mp.player_id, mp.match.tournament_id, mp.match.event)
                ro = mp.match.round_order or 0
                cur = best.get(key)
                if cur is None or ro > cur[0]:
                    best[key] = (ro, mp.match.round_name, mp.match.winner_side == mp.side)

        friendly = {"SF": "Semi-final", "QF": "Quarter-final", "R16": "Last 16",
                    "R32": "Last 32", "R64": "Last 64", "R128": "Last 128"}
        for tp, r in zip(picked, rows):
            info = best.get((tp.player_id, tp.tournament_id, tp.event))
            if not info:
                r["achievement"] = None
                continue
            _, round_name, won = info
            if round_name in ("Final", "F"):
                r["achievement"] = "Champion" if won else "Runner-up"
            else:
                r["achievement"] = friendly.get(round_name, round_name or None)

    def _enrich_upsets(self, picked, rows):
        ids = [tp.best_match_id for tp in picked if tp.best_match_id]
        matches = {
            m.match_id: m
            for m in Match.objects.filter(match_id__in=ids).prefetch_related(
                "lineup__player"
            )
        }
        for tp, r in zip(picked, rows):
            m = matches.get(tp.best_match_id)
            if not m:
                r["best_round"], r["beat"] = None, []
                continue
            side = next(
                (l.side for l in m.lineup.all() if l.player_id == tp.player_id), None
            )
            r["best_round"] = m.round_name
            r["beat"] = PlayerBriefSerializer(
                [l.player for l in m.lineup.all() if l.side != side], many=True
            ).data


class EventsView(APIView):
    """GET /api/events — the discipline buckets and their rated-player counts."""

    def get(self, request):
        counts = {
            e: PlayerRating.objects.filter(event=e).count() for e in EVENTS
        }
        return Response(
            [{"event": e, "rated_players": counts[e]} for e in EVENTS]
        )


# (event, kind, slots) per cup — the disciplines a national team fields.
CUP_SPECS = {
    "thomas": [("MS", "single", 3), ("MD", "pair", 2)],   # men's team
    "uber": [("WS", "single", 3), ("WD", "pair", 2)],      # women's team
    "sudirman": [                                          # mixed team
        ("MS", "single", 1), ("WS", "single", 1),
        ("MD", "pair", 1), ("WD", "pair", 1), ("XD", "pair", 1),
    ],
}


class CupView(APIView):
    """GET /api/cups/{thomas|uber|sudirman} — national team power.

    A country's power is the sum of its strongest ACTIVE players/pairs for the
    disciplines that cup contests (Thomas = 3 MS + 2 MD, Uber = 3 WS + 2 WD,
    Sudirman = 1 of each of MS/WS/MD/WD/XD). Retired players (idle > 1 year) are
    excluded, so the table reflects who could field a team right now. Only
    countries able to fill every slot are ranked.
    """

    def get(self, request, cup):
        spec = CUP_SPECS.get(cup)
        if not spec:
            raise ValidationError({"cup": f"one of {', '.join(CUP_SPECS)}"})
        cutoff = active_cutoff()

        # country -> {slot_key: [(rating_value, contributor_dict), ...]}
        by_country: dict = defaultdict(dict)
        for event, kind, slots in spec:
            per: dict = defaultdict(list)
            if kind == "single":
                for r in PlayerRating.objects.filter(
                    event=event, last_match_utc__gte=cutoff
                ).select_related("player"):
                    cc = r.player.country_code
                    if cc:
                        per[cc].append(
                            (r.mu, {
                                "event": event, "rating": round(r.mu),
                                "players": [PlayerBriefSerializer(r.player).data],
                            })
                        )
            else:
                for p in Partnership.objects.filter(
                    event=event, last_match_utc__gte=cutoff
                ).select_related("player1", "player2"):
                    cc = p.player1.country_code
                    if cc and cc == p.player2.country_code:
                        per[cc].append(
                            (p.combined_mu, {
                                "event": event, "rating": round(p.combined_mu),
                                "players": PlayerBriefSerializer(
                                    [p.player1, p.player2], many=True
                                ).data,
                            })
                        )
            key = f"{event}:{kind}"
            for cc, items in per.items():
                items.sort(key=lambda it: it[0], reverse=True)
                by_country[cc][key] = items[:slots]

        rows = []
        for cc, slotmap in by_country.items():
            if any(
                len(slotmap.get(f"{e}:{k}", [])) < n for e, k, n in spec
            ):
                continue  # can't field a full team
            contributors, power = [], 0.0
            for e, k, n in spec:
                for value, c in slotmap[f"{e}:{k}"]:
                    power += value
                    contributors.append(c)
            rows.append(
                {"country": cc, "power": round(power), "contributors": contributors}
            )
        rows.sort(key=lambda r: r["power"], reverse=True)
        return Response({"cup": cup, "results": rows})
