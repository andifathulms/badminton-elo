"""DRF read-only views (PRD §12).

    GET /api/leaderboard?event=XD[&min_matches=5&order=rating|mu]
    GET /api/players/{id}
    GET /api/players/{id}/history?event=XD
    GET /api/matches/{id}
    GET /api/events
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Avg, Count, DateTimeField, F, FloatField, Max
from django.db.models.functions import Cast, Coalesce, Round
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
    MatchStatistics,
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
    TournamentBriefSerializer,
    TournamentListSerializer,
    TournamentPerformanceSerializer,
)

EVENTS = ("MS", "WS", "MD", "WD", "XD")
DOUBLES = ("MD", "WD", "XD")


def team_cup_kind(t):
    """'thomas' | 'uber' | 'sudirman' | 'team' | None — is this tournament a
    team competition (nation vs nation, rubbers grouped into ties)?"""
    hay = f"{t.name or ''} {t.category_name or ''}".lower()
    if "sudirman cup" in hay:
        return "sudirman"
    if "thomas cup" in hay:
        return "thomas"
    if "uber cup" in hay:
        return "uber"
    if "team championship" in hay or "team event" in hay or (
        "team" in hay and "cup" in hay
    ):
        return "team"
    return None


def _side_country(players):
    """The country a rubber side represents: the most common player country."""
    from collections import Counter

    c = Counter(p.country_code for p in players if p.country_code)
    return c.most_common(1)[0][0] if c else None


def _rubber_discipline(s1, s2):
    """Discipline of a team-cup rubber for display: the gender-inferred value,
    or a bare S/D from player count when gender is unknown."""
    from apps.ingest.cup_events import rubber_discipline

    return rubber_discipline(s1, s2) or ("S" if max(len(s1), len(s2)) == 1 else "D")

# Full tournament prestige order (top = most prestigious). Multi-sport events and
# team cups sit above the BWF World Tour, then development tiers. Anything
# unlisted sorts last. Used by the tournament "master" (by-year) overview.
# Tournament sections follow BWF's official grading (Wikipedia "BWF events"):
#   Grade 1 (S-Tier) — WC, Thomas/Uber/Sudirman, Olympics, + Junior/Senior/Para
#   Continental Games — Asian/SEA/Commonwealth/etc. multi-sport & continental
#   Grade 2 (A-Tier)  — BWF World Tour (Finals, Super 1000..100) + predecessors
#   Grade 3 (B-Tier)  — Continental Circuit (Int'l Challenge/Series/Future)
GRADE1 = {
    "Olympics", "World Championships",
    "Thomas Cup", "Uber Cup", "Sudirman Cup",
    "Grade 1 – Individual Tournaments", "Grade 1 – Team Tournaments",
    "Grade 1 – Individual Senior Tournaments",
}
CONTINENTAL = {
    "Asian Games", "Commonwealth Games", "European Games", "Pan American Games",
    "African Games", "SEA Games", "Continental Individual Games",
    "Continental Team Games", "Continental Individual Championships",
    "Continental Team Championships",
}
PRESTIGE_ORDER = [
    # Grade 1 (S-Tier) — Main then Others
    "Olympics", "World Championships",
    "Thomas Cup", "Uber Cup", "Sudirman Cup",
    "Grade 1 – Individual Tournaments", "Grade 1 – Team Tournaments",
    "Grade 1 – Individual Senior Tournaments",
    # Continental Games
    "Asian Games", "Commonwealth Games", "European Games",
    "Pan American Games", "African Games", "SEA Games",
    "Continental Individual Games", "Continental Team Games",
    "Continental Individual Championships", "Continental Team Championships",
    # Grade 2 (BWF World Tour) — by level
    "HSBC BWF World Tour Finals", "World Tour Finals",
    "HSBC BWF World Tour Super 1000", "All England",
    "HSBC BWF World Tour Super 750", "HSBC BWF World Tour Super 500",
    "HSBC BWF World Tour Super 300", "BWF Tour Super 100",
    "World Superseries Premier", "World Superseries",
    "Grand Prix Gold", "Grand Prix",
    # Grade 3 (Continental Circuit)
    "International Challenge", "International Series", "Future Series",
    "BWF Events", "Other",
]
_PRESTIGE_RANK = {name: i for i, name in enumerate(PRESTIGE_ORDER)}

# Broad section a tier belongs to (for the master view's group headers).
def prestige_group(category: str) -> str:
    if category in GRADE1:
        return "🥇 Grade 1 (S-Tier)"
    if category in CONTINENTAL:
        return "🌏 Continental Games"
    if any(k in category for k in ("World Tour", "Superseries", "Grand Prix",
                                   "All England", "Super 100")):
        return "🌐 Grade 2 · BWF World Tour"
    return "🏸 Grade 3 · Continental Circuit"
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


class H2HView(APIView):
    """GET /api/h2h?event=&p1=&p2= — a head-to-head matchup between two players
    in one discipline: each side's current rating, a Glicko-2 win probability,
    and every past meeting (they were on OPPOSITE sides) with the running record.

    Works for any discipline — the two players' individual (player, event)
    ratings drive the prediction, so singles is the natural case but a mixed or
    doubles pair of rivals compares their personal ratings too.
    """

    def get(self, request):
        from .predict import win_probability

        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})
        try:
            p1 = int(request.query_params["p1"])
            p2 = int(request.query_params["p2"])
        except (KeyError, ValueError):
            raise ValidationError({"detail": "event, p1, p2 required"})
        if p1 == p2:
            raise ValidationError({"detail": "p1 and p2 must differ"})

        players = {p.player_id: p for p in Player.objects.filter(player_id__in=(p1, p2))}
        if p1 not in players or p2 not in players:
            raise ValidationError({"detail": "unknown player"})
        ratings = {
            r.player_id: r
            for r in PlayerRating.objects.filter(player_id__in=(p1, p2), event=event)
        }

        def rating_block(pid):
            r = ratings.get(pid)
            if not r:
                return None
            return {
                "mu": round(r.mu, 1), "rd": round(r.rd, 1),
                "rating": round(r.mu - 2.0 * r.rd, 1),
                "peak_mu": round(r.peak_mu, 1) if r.peak_mu is not None else None,
                "matches_played": r.matches_played,
            }

        r1, r2 = rating_block(p1), rating_block(p2)
        prob = (
            round(win_probability(ratings[p1].mu, ratings[p1].rd,
                                  ratings[p2].mu, ratings[p2].rd), 4)
            if r1 and r2 else None
        )

        # Meetings: matches in this event where p1 and p2 were on opposite sides.
        s1 = dict(
            MatchPlayer.objects.filter(player_id=p1, match__event=event)
            .values_list("match_id", "side")
        )
        s2 = dict(
            MatchPlayer.objects.filter(player_id=p2, match__event=event)
            .values_list("match_id", "side")
        )
        shared = [mid for mid, side in s1.items() if s2.get(mid) not in (None, side)]
        matches = (
            Match.objects.filter(match_id__in=shared)
            .select_related("tournament")
            .prefetch_related("lineup__player", "games")
            .order_by("-match_time_utc", "-match_id")
        )

        meetings, w1, w2 = [], 0, 0
        for m in matches:
            side1 = s1[m.match_id]  # p1's side in this match
            lineup = list(m.lineup.all())
            games = [
                [g.side1_points, g.side2_points]
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            if side1 == 2:  # orient the score to p1's perspective
                games = [[b, a] for a, b in games]
            p1_won = m.winner_side == side1
            if m.winner_side in (1, 2):
                w1 += p1_won
                w2 += not p1_won
            meetings.append({
                "match_id": m.match_id,
                "event": m.event,
                "round_name": m.round_name,
                "match_time_utc": m.match_time_utc,
                "tournament": TournamentBriefSerializer(m.tournament).data
                if m.tournament_id else None,
                "p1_won": p1_won if m.winner_side in (1, 2) else None,
                "score": games,
                "score_status": m.score_status,
                "p1_partners": PlayerBriefSerializer(
                    [l.player for l in lineup if l.side == side1 and l.player_id != p1],
                    many=True,
                ).data,
                "p2_partners": PlayerBriefSerializer(
                    [l.player for l in lineup if l.side != side1 and l.player_id != p2],
                    many=True,
                ).data,
            })

        return Response({
            "event": event,
            "player1": {**PlayerBriefSerializer(players[p1]).data, "rating": r1},
            "player2": {**PlayerBriefSerializer(players[p2]).data, "rating": r2},
            "win_prob": prob,
            "record": {"p1_wins": w1, "p2_wins": w2, "meetings": len(meetings)},
            "meetings": meetings,
        })


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


def _team_rating(members):
    """Conservative side rating from members' (mu, rd): mean(mu) − 2·RMS(rd).
    Mirrors how pair strength is combined elsewhere. None if no data."""
    members = [(mu, rd) for mu, rd in members if mu is not None and rd is not None]
    if not members:
        return None
    mean_mu = sum(mu for mu, _ in members) / len(members)
    rms_rd = (sum(rd * rd for _, rd in members) / len(members)) ** 0.5
    return round(mean_mu - 2.0 * rms_rd)


def _match_card(m):
    """Compact match descriptor: both sides (as pairs), score, tournament, round."""
    lineup = sorted(m.lineup.all(), key=lambda l: l.side)
    side1 = [l.player for l in lineup if l.side == 1]
    side2 = [l.player for l in lineup if l.side == 2]
    games = [
        [g.side1_points, g.side2_points]
        for g in sorted(m.games.all(), key=lambda g: g.game_no)
    ]
    return {
        "match_id": m.match_id,
        "event": m.event,
        "round_name": m.round_name,
        "match_time_utc": m.match_time_utc,
        "tournament": {"id": m.tournament_id, "name": m.tournament.name},
        "winner_side": m.winner_side,
        "score": games,
        "side1": PlayerBriefSerializer(side1, many=True).data,
        "side2": PlayerBriefSerializer(side2, many=True).data,
    }


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
    def master(self, request):
        """GET /api/tournaments/master?year=Y — every tournament that year,
        sorted by prestige (multi-sport & championships on top), each tagged
        with its section group. Powers the by-year 'tournament master' view."""
        year = request.query_params.get("year")
        qs = Tournament.objects.annotate(match_count=Count("matches"))
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

    @action(detail=True, methods=["get"])
    def ties(self, request, tournament_id=None):
        """GET /api/tournaments/{id}/ties — a team cup as nation-vs-nation ties.

        Rubbers (individual matches) are grouped into ties: within a round, a run
        of consecutive matches sharing the same pair of countries is one tie. Each
        rubber's true discipline is inferred from its lineup (the stored `event`
        is unreliable on team cups). Sides are oriented so country1 reads first.
        """
        from .elo import tournament_match_elo

        t = self.get_object()
        kind = team_cup_kind(t)
        matches = list(
            Match.objects.filter(tournament=t)
            .prefetch_related("lineup__player", "games")
            .order_by("round_order", "match_id")
        )
        elo_map = tournament_match_elo(int(tournament_id))

        # Bucket by round, preserving round order.
        rounds: dict = {}
        for m in matches:
            rounds.setdefault((m.round_order or 0, m.round_name), []).append(m)

        def side_elo(mid, players):
            ds = [elo_map.get(mid, {}).get(p.player_id) for p in players]
            ds = [d[2] for d in ds if d]
            return round(sum(ds) / len(ds), 1) if ds else None

        def build_rubber(m, s1, s2, c1, c2, country1, country2, order):
            games = [
                [g.side1_points, g.side2_points]
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            win = m.winner_side
            # Orient so country1's players read as side1. Works even when a side's
            # country is unknown, by matching against the tie's two nations.
            swap = (c1 is not None and c1 == country2) or (c2 is not None and c2 == country1)
            if swap:
                s1, s2 = s2, s1
                games = [[b, a] for a, b in games]
                win = {1: 2, 2: 1}.get(win)
            return {
                "match_id": m.match_id,
                "order": order,
                "discipline": _rubber_discipline(s1, s2),
                "side1": PlayerBriefSerializer(s1, many=True).data,
                "side2": PlayerBriefSerializer(s2, many=True).data,
                "winner_side": win,
                "score": games,
                "score_status": m.score_status,
                "elo1": side_elo(m.match_id, s1),
                "elo2": side_elo(m.match_id, s2),
            }

        out_rounds = []
        champion = None
        for (rorder, rname), ms in sorted(rounds.items()):
            # Group consecutive rubbers into ties. A tie has at most two nations;
            # a rubber joins the current tie as long as that stays true (so a
            # rubber whose opponent has no country_code doesn't split the tie).
            raw = []
            for m in ms:
                s1 = [l.player for l in m.lineup.all() if l.side == 1]
                s2 = [l.player for l in m.lineup.all() if l.side == 2]
                c1, c2 = _side_country(s1), _side_country(s2)
                known = {c for c in (c1, c2) if c}
                cur = raw[-1] if raw else None
                if cur is not None and len(cur["countries"] | known) <= 2:
                    cur["countries"] |= known
                else:
                    cur = {"countries": set(known), "rubbers": []}
                    raw.append(cur)
                cur["rubbers"].append((m, s1, s2, c1, c2))

            ties = []
            for i, rt in enumerate(raw, 1):
                cs = rt["countries"]
                first = rt["rubbers"][0]
                country1 = (first[3] if first[3] in cs
                            else first[4] if first[4] in cs
                            else next(iter(cs), None))
                country2 = next((c for c in cs if c != country1), None)
                rubbers, s1c, s2c = [], 0, 0
                for j, (m, s1, s2, c1, c2) in enumerate(rt["rubbers"], 1):
                    r = build_rubber(m, s1, s2, c1, c2, country1, country2, j)
                    rubbers.append(r)
                    if r["winner_side"] == 1:
                        s1c += 1
                    elif r["winner_side"] == 2:
                        s2c += 1
                ties.append({
                    "order": i,
                    "country1": country1, "country2": country2,
                    "score1": s1c, "score2": s2c,
                    "winner_country": (country1 if s1c > s2c
                                       else country2 if s2c > s1c else None),
                    "rubbers": rubbers,
                })
            out_rounds.append({
                "round_name": rname, "round_order": rorder, "ties": ties,
            })
            if rname in ("Final", "F") and len(ties) == 1:
                champion = ties[0]["winner_country"]

        return Response({
            "is_team_cup": kind is not None,
            "cup": kind,
            "champion": champion,
            "rounds": out_rounds,
        })

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

        # Upsets are ranked per MATCH (every standout single win), not per
        # tournament-performance — a pair can appear twice in one tournament.
        if kind == "upsets":
            return self._match_upsets(request, event, limit)

        qs = TournamentPerformance.objects.select_related(
            "player", "partner", "tournament"
        ).filter(matches__gte=min_matches)
        if event in EVENTS:
            qs = qs.filter(event=event)
        if request.query_params.get("include_new") != "1":
            qs = qs.filter(rd_start__lte=130)
        if kind == "performances":
            qs = qs.exclude(perf_rating=None).order_by("-perf_rating")
        else:
            qs = qs.order_by("-net_delta")

        # Collapse the two members of a doubles pair into one row. partner_id can
        # be missing on some performances, so also collapse by the shared match:
        # two winners of the same match are the same pair.
        seen: set = set()
        picked: list = []
        for tp in qs[:2000]:
            if len(picked) >= limit:
                break
            if tp.event in DOUBLES:
                keys = []
                if tp.partner_id:
                    keys.append(
                        (tp.tournament_id, tp.event,
                         frozenset((tp.player_id, tp.partner_id)))
                    )
                if tp.best_match_id:
                    keys.append(("match", tp.best_match_id))
                if any(k in seen for k in keys):
                    continue
                seen.update(keys)
            picked.append(tp)

        rows = TournamentPerformanceSerializer(picked, many=True).data
        self._enrich_achievement(picked, rows)
        return Response({"results": rows})

    def _match_upsets(self, request, event, limit):
        """Biggest single-match upsets: rank individual wins by ELO gained.
        A positive delta means the player won and gained, so the winning side
        is exactly the players with a positive delta. Collapsed to one row per
        match (both partners for doubles)."""
        include_new = request.query_params.get("include_new") == "1"
        # delta >= 30 keeps the sort cheap; any upset that makes a list is well
        # above it. Highest first, so the first row seen per match is its top
        # winner (and carries the pair).
        rh = RatingHistory.objects.filter(delta__gte=30)
        if event in EVENTS:
            rh = rh.filter(event=event)
        if not include_new:
            rh = rh.filter(rd_before__lte=130)
        rh = rh.order_by("-delta").values(
            "match_id", "player_id", "delta"
        )
        seen: set = set()
        picks: list = []
        for r in rh[:5000]:
            if r["match_id"] in seen:
                continue
            seen.add(r["match_id"])
            picks.append(r)
            if len(picks) >= limit:
                break

        ids = [p["match_id"] for p in picks]
        matches = {
            m.match_id: m
            for m in Match.objects.filter(match_id__in=ids)
            .select_related("tournament")
            .prefetch_related("lineup__player", "games")
        }
        pre = {
            (mid, pid): (mu, rd)
            for mid, pid, mu, rd in RatingHistory.objects.filter(
                match_id__in=ids
            ).values_list("match_id", "player_id", "mu_before", "rd_before")
        }

        out = []
        for p in picks:
            m = matches.get(p["match_id"])
            if not m:
                continue
            lineup = list(m.lineup.all())
            side = next(
                (l.side for l in lineup if l.player_id == p["player_id"]), None
            )
            winners = [l.player for l in lineup if l.side == side]
            opp = [l.player for l in lineup if l.side != side]
            player = next(
                (pl for pl in winners if pl.player_id == p["player_id"]), winners[0]
            )
            partner = next(
                (pl for pl in winners if pl.player_id != p["player_id"]), None
            )
            games = [
                (g.side1_points, g.side2_points)
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            if side == 2:
                games = [(b, a) for a, b in games]
            out.append({
                "player": PlayerBriefSerializer(player).data,
                "partner": PlayerBriefSerializer(partner).data if partner else None,
                "event": m.event,
                "tournament": TournamentBriefSerializer(m.tournament).data,
                "best_delta": round(p["delta"], 1),
                "best_match": m.match_id,
                "best_round": m.round_name,
                "beat": PlayerBriefSerializer(opp, many=True).data,
                "best_score": games,
                "best_score_status": m.score_status,
                "winner_rating_before": _team_rating(
                    [pre.get((m.match_id, l.player_id)) or (None, None)
                     for l in lineup if l.side == side]
                ),
                "opponent_rating_before": _team_rating(
                    [pre.get((m.match_id, l.player_id)) or (None, None)
                     for l in lineup if l.side != side]
                ),
            })
        return Response({"results": out})

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


class CalibrationView(APIView):
    """GET /api/analytics/calibration?event= — rating reliability.

    Returns the predicted-vs-actual win rate per probability bucket (a
    reliability diagram) plus the headline accuracy: how often the higher-rated
    side actually wins. event defaults to ALL (every discipline pooled).
    """

    def get(self, request):
        from apps.ingest.models import CalibrationBin

        event = request.query_params.get("event") or "ALL"
        if event not in EVENTS and event != "ALL":
            raise ValidationError({"event": f"one of ALL, {', '.join(EVENTS)}"})
        rows = list(CalibrationBin.objects.filter(event=event).order_by("bucket"))
        bins = [
            {
                "bucket": r.bucket,
                "lo": round(r.bucket / 10, 2),
                "hi": round((r.bucket + 1) / 10, 2),
                "n": r.n,
                "predicted": round(r.prob_sum / r.n, 4) if r.n else None,
                "actual": round(r.correct / r.n, 4) if r.n else None,
            }
            for r in rows
        ]
        n = sum(r.n for r in rows)
        correct = sum(r.correct for r in rows)
        # Mean calibration error: |predicted − actual| weighted by bucket size.
        ece = (
            sum(abs(b["predicted"] - b["actual"]) * b["n"] for b in bins if b["n"])
            / n
            if n else None
        )
        return Response({
            "event": event,
            "n": n,
            "accuracy": round(correct / n, 4) if n else None,
            "calibration_error": round(ece, 4) if ece is not None else None,
            "bins": bins,
        })


class ClutchView(APIView):
    """GET /api/analytics/clutch?event=[&min=&limit=&order=] — deciding-game
    leaderboard: who wins the matches that go the distance to a third game.

    Ranked by third-game win rate among players with at least `min` deciding
    games (default 15), so a small sample can't top the board. order=played
    ranks by sheer volume of deciders instead.
    """

    def get(self, request):
        from apps.ingest.models import ClutchStat

        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})
        try:
            min_dec = int(request.query_params.get("min", 15))
        except ValueError:
            min_dec = 15
        try:
            limit = min(int(request.query_params.get("limit", 40)), 100)
        except ValueError:
            limit = 40

        qs = (
            ClutchStat.objects.filter(event=event, deciders_played__gte=min_dec)
            .select_related("player")
        )
        rows = [
            {
                "player": PlayerBriefSerializer(c.player).data,
                "deciders_played": c.deciders_played,
                "deciders_won": c.deciders_won,
                "decider_pct": round(100.0 * c.deciders_won / c.deciders_played, 1),
                "matches": c.matches,
                "overall_pct": round(100.0 * c.wins / c.matches, 1) if c.matches else None,
            }
            for c in qs
        ]
        if request.query_params.get("order") == "played":
            rows.sort(key=lambda r: (r["deciders_played"], r["decider_pct"]), reverse=True)
        else:
            rows.sort(key=lambda r: (r["decider_pct"], r["deciders_played"]), reverse=True)
        return Response({"event": event, "min": min_dec, "results": rows[:limit]})


class AgingView(APIView):
    """GET /api/analytics/aging?event=[&min_matches=] — when players peak.

    Uses each rated player's all-time peak (peak_mu at peak_utc) and date of
    birth to place their career peak on an age axis: the age distribution of
    peaks, the median peak age, and the average peak rating per age — so you can
    see the window a discipline's players tend to be at their best.
    event omitted pools all five main disciplines.
    """

    AGE_MIN, AGE_MAX = 14, 42

    def get(self, request):
        event = request.query_params.get("event")
        if event and event not in EVENTS:
            raise ValidationError({"event": f"one of {', '.join(EVENTS)}"})
        try:
            min_matches = int(request.query_params.get("min_matches", 20))
        except ValueError:
            min_matches = 20

        qs = (
            PlayerRating.objects.filter(matches_played__gte=min_matches)
            .exclude(peak_mu=None).exclude(peak_utc=None)
            .filter(player__dob__isnull=False)
            .select_related("player")
        )
        qs = qs.filter(event=event) if event else qs.filter(event__in=EVENTS)

        ages: list[float] = []
        by_age: dict = defaultdict(lambda: {"n": 0, "mu_sum": 0.0})
        top: list = []
        for r in qs:
            dob = r.player.dob
            peak = r.peak_utc
            age = (peak.date() - dob).days / 365.25
            if not (self.AGE_MIN <= age <= self.AGE_MAX):
                continue
            ages.append(age)
            b = by_age[int(age)]
            b["n"] += 1
            b["mu_sum"] += r.peak_mu
            top.append((r.peak_mu, age, r.player, r.event))

        if not ages:
            return Response({"event": event or "ALL", "n": 0, "bins": []})

        ages.sort()
        n = len(ages)
        median = ages[n // 2] if n % 2 else (ages[n // 2 - 1] + ages[n // 2]) / 2
        bins = [
            {"age": age, "count": b["n"], "avg_peak": round(b["mu_sum"] / b["n"], 1)}
            for age, b in sorted(by_age.items())
        ]
        top.sort(key=lambda t: t[0], reverse=True)
        peakers = [
            {
                "player": PlayerBriefSerializer(p).data,
                "event": ev,
                "peak_mu": round(mu, 1),
                "peak_age": round(age, 1),
            }
            for mu, age, p, ev in top[:10]
        ]
        return Response({
            "event": event or "ALL",
            "n": n,
            "median_peak_age": round(median, 1),
            "mean_peak_age": round(sum(ages) / n, 1),
            "bins": bins,
            "peakers": peakers,
        })


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


class CupHistoryView(APIView):
    """GET /api/cups/{cup}/history — each top country's team power per year, so
    the Cups timeline shows dominance eras."""

    def get(self, request, cup):
        from apps.ingest.models import CupPowerHistory

        if cup not in CUP_SPECS:
            raise ValidationError({"cup": f"one of {', '.join(CUP_SPECS)}"})
        rows = list(
            CupPowerHistory.objects.filter(cup=cup).values("country", "year", "power")
        )
        if not rows:
            return Response({"cup": cup, "years": [], "series": []})
        years = sorted({r["year"] for r in rows})
        by_country: dict = defaultdict(dict)
        peak: dict = defaultdict(float)
        for r in rows:
            by_country[r["country"]][r["year"]] = r["power"]
            peak[r["country"]] = max(peak[r["country"]], r["power"])
        top = sorted(peak, key=peak.get, reverse=True)[:8]
        series = [
            {
                "country": cc,
                "points": [
                    {"year": y, "power": by_country[cc].get(y)} for y in years
                ],
            }
            for cc in top
        ]
        return Response({"cup": cup, "years": years, "series": series})
