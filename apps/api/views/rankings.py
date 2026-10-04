"""Ranking boards and matchups: individual leaderboard, pairs, a pair's
detail, and head-to-head."""
from __future__ import annotations

from collections import defaultdict

from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import Match, MatchPlayer, Partnership, Player, PlayerRating

from ..serializers import (
    LeaderboardEntrySerializer,
    MatchListSerializer,
    PairSerializer,
    PlayerBriefSerializer,
    TournamentBriefSerializer,
)
from .common import DOUBLES, EVENTS, active_cutoff


def _is_default_board(qp) -> bool:
    """The board `rate`/`build_movement` pre-rank: current, by conservative
    rating, >= 5 matches, active players only."""
    return (
        qp.get("ranking", "current") == "current"
        and qp.get("order", "rating") == "rating"
        and qp.get("min_matches", "5") == "5"
        and qp.get("include_inactive") != "1"
    )


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

        qp = self.request.query_params
        # The default board (current, by rating, >= 5 matches, active) is ranked
        # once by `rate`/`build_movement` — read the stored rank (indexed).
        if _is_default_board(qp):
            field = "rank_gender" if gender in ("M", "F") else "rank"
            return qs.filter(**{f"{field}__isnull": False}).order_by(field)

        # Current board: hide retired players (idle > 1 year) unless asked.
        if qp.get("include_inactive") != "1":
            qs = qs.filter(last_match_utc__gte=active_cutoff())

        order = qp.get("order", "rating")
        if order == "mu":
            return qs.order_by("-mu", "rd")
        # conservative rating = mu - 2*rd (a stored, indexed column)
        return qs.order_by("-rating")

    def list(self, request, *args, **kwargs):
        """Add each row's record, form line and rank movement — all stored on
        PlayerRating by `rate`/`build_movement`, so no extra queries."""
        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        data = self.get_serializer(rows, many=True).data

        qp = request.query_params
        default_board = _is_default_board(qp)
        gendered = qp.get("gender") in ("M", "F")
        for row, pr in zip(data, rows):
            # Form: the rating carried into each recent tournament, then today's.
            row["form"] = list(pr.form or []) + [round(pr.mu)]
            if default_board:
                now, prev = (
                    (pr.rank_gender, pr.rank_prev_gender) if gendered else (pr.rank, pr.rank_prev)
                )
                row["rank_change"] = (prev - now) if (now and prev) else None
            played = pr.wins + pr.losses
            row["wins"], row["losses"] = pr.wins, pr.losses
            row["win_pct"] = round(100.0 * pr.wins / played, 1) if played else None
        return self.get_paginated_response(data)


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
        return qs.order_by("-rating")


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
    """GET /api/h2h?event=&s1=&s2= — a head-to-head matchup in one discipline.

    Each side is 1 player (singles) or a pair (doubles), given as a comma list of
    ids: `s1=57945` or `s1=52749,54066`. Returns each side's combined rating, a
    Glicko-2 win probability (team = mean mu, RMS rd — same blend as everywhere),
    and every past meeting where those exact players faced each other, with the
    running record. `p1`/`p2` are still accepted as single-player aliases so the
    profile deep-link keeps working.
    """

    def get(self, request):
        from rating.predict import team_rating, win_probability

        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})

        def parse_side(*keys):
            for k in keys:
                v = request.query_params.get(k)
                if v:
                    try:
                        return [int(x) for x in v.split(",") if x != ""]
                    except ValueError:
                        raise ValidationError({k: "must be player id(s)"})
            return []

        s1_ids = parse_side("s1", "p1")
        s2_ids = parse_side("s2", "p2")
        cap = 2 if event in DOUBLES else 1
        if not (1 <= len(s1_ids) <= cap) or not (1 <= len(s2_ids) <= cap):
            raise ValidationError(
                {"detail": f"each side needs 1{'-2' if cap == 2 else ''} player(s) for {event}"}
            )
        if set(s1_ids) & set(s2_ids):
            raise ValidationError({"detail": "a player can't be on both sides"})

        all_ids = s1_ids + s2_ids
        players = {p.player_id: p for p in Player.objects.filter(player_id__in=all_ids)}
        if any(pid not in players for pid in all_ids):
            raise ValidationError({"detail": "unknown player"})
        ratings = {
            r.player_id: r
            for r in PlayerRating.objects.filter(player_id__in=all_ids, event=event)
        }

        def side_block(ids):
            members = [(ratings[i].mu, ratings[i].rd) for i in ids if i in ratings]
            team = team_rating(members) if len(members) == len(ids) else None
            return {
                "players": PlayerBriefSerializer(
                    [players[i] for i in ids], many=True
                ).data,
                "rating": None if not team else {
                    "mu": round(team[0], 1), "rd": round(team[1], 1),
                    "rating": round(team[0] - 2.0 * team[1], 1),
                },
            }

        b1, b2 = side_block(s1_ids), side_block(s2_ids)
        prob = None
        if b1["rating"] and b2["rating"]:
            t1 = team_rating([(ratings[i].mu, ratings[i].rd) for i in s1_ids])
            t2 = team_rating([(ratings[i].mu, ratings[i].rd) for i in s2_ids])
            prob = round(win_probability(t1[0], t1[1], t2[0], t2[1]), 4)

        # Meetings: matches in this event where ALL of s1 were on one side and ALL
        # of s2 on the other (so the exact pairing actually faced off).
        per_match: dict = defaultdict(dict)  # match_id -> {player_id: side}
        for mid, pid, side in (
            MatchPlayer.objects.filter(player_id__in=all_ids, match__event=event)
            .values_list("match_id", "player_id", "side")
        ):
            per_match[mid][pid] = side
        shared = {}
        for mid, d in per_match.items():
            if not all(p in d for p in all_ids):
                continue
            side1 = {d[p] for p in s1_ids}
            side2 = {d[p] for p in s2_ids}
            if len(side1) == 1 and len(side2) == 1 and side1 != side2:
                shared[mid] = side1.pop()  # s1's side in this match

        matches = (
            Match.objects.filter(match_id__in=list(shared))
            .select_related("tournament")
            .prefetch_related("lineup__player", "games")
            .order_by("-match_time_utc", "-match_id")
        )

        meetings, w1, w2 = [], 0, 0
        for m in matches:
            side1 = shared[m.match_id]
            lineup = list(m.lineup.all())
            games = [
                [g.side1_points, g.side2_points]
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            if side1 == 2:  # orient the score to side 1's perspective
                games = [[b, a] for a, b in games]
            s1_won = m.winner_side == side1
            if m.winner_side in (1, 2):
                w1 += s1_won
                w2 += not s1_won
            meetings.append({
                "match_id": m.match_id,
                "event": m.event,
                "round_name": m.round_name,
                "match_time_utc": m.match_time_utc,
                "tournament": TournamentBriefSerializer(m.tournament).data
                if m.tournament_id else None,
                "p1_won": s1_won if m.winner_side in (1, 2) else None,
                "score": games,
                "score_status": m.score_status,
                # Any extra players on court not in the selected pairing (rare).
                "p1_partners": PlayerBriefSerializer(
                    [l.player for l in lineup
                     if l.side == side1 and l.player_id not in s1_ids],
                    many=True,
                ).data,
                "p2_partners": PlayerBriefSerializer(
                    [l.player for l in lineup
                     if l.side != side1 and l.player_id not in s2_ids],
                    many=True,
                ).data,
            })

        return Response({
            "event": event,
            "side1": b1,
            "side2": b2,
            "win_prob": prob,
            "record": {"p1_wins": w1, "p2_wins": w2, "meetings": len(meetings)},
            "meetings": meetings,
        })
