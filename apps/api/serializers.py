"""DRF serializers for the read API (PRD §12).

Read-only projections of the ingest + rating models. `rating` (mu − 2·rd) is a
conservative score so an uncertain player can't top a board on a small sample.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.ingest.models import (
    Game,
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


class MatchStatisticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchStatistics
        fields = (
            "team1_rallies_won",
            "team1_rallies_played",
            "team2_rallies_won",
            "team2_rallies_played",
            "team1_consecutive_points",
            "team2_consecutive_points",
            "team1_game_points",
            "team2_game_points",
            "duration_min",
            "point_progression",
        )


class PlayerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ("player_id", "name_display", "country_code", "avatar_url")


class PairSerializer(serializers.ModelSerializer):
    player1 = PlayerBriefSerializer(read_only=True)
    player2 = PlayerBriefSerializer(read_only=True)
    rating = serializers.SerializerMethodField()
    peak_rating = serializers.SerializerMethodField()
    win_pct = serializers.SerializerMethodField()

    class Meta:
        model = Partnership
        fields = (
            "event",
            "player1",
            "player2",
            "rating",
            "peak_rating",
            "combined_mu",
            "combined_rd",
            "combined_peak_mu",
            "matches_together",
            "wins_together",
            "win_pct",
            "last_match_utc",
        )

    def get_rating(self, obj) -> float:
        return round(obj.combined_mu - 2.0 * obj.combined_rd, 1)

    def get_peak_rating(self, obj):
        if obj.combined_peak_mu is None:
            return None
        return round(obj.combined_peak_mu, 1)

    def get_win_pct(self, obj):
        if not obj.matches_together:
            return None
        return round(100.0 * obj.wins_together / obj.matches_together, 1)


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    player = PlayerBriefSerializer(read_only=True)
    rating = serializers.SerializerMethodField()
    peak_rating = serializers.SerializerMethodField()

    class Meta:
        model = PlayerRating
        fields = (
            "player",
            "event",
            "rating",
            "peak_rating",
            "mu",
            "rd",
            "peak_mu",
            "peak_rd",
            "peak_utc",
            "sigma",
            "matches_played",
            "last_match_utc",
        )

    def get_rating(self, obj) -> float:
        return round(obj.mu - 2.0 * obj.rd, 1)

    def get_peak_rating(self, obj):
        if obj.peak_mu is None:
            return None
        return round(obj.peak_mu, 1)


class PlayerRatingSerializer(serializers.ModelSerializer):
    rating = serializers.SerializerMethodField()

    class Meta:
        model = PlayerRating
        fields = (
            "event",
            "rating",
            "mu",
            "rd",
            "peak_mu",
            "peak_rd",
            "peak_utc",
            "sigma",
            "matches_played",
            "last_match_utc",
        )

    def get_rating(self, obj) -> float:
        return round(obj.mu - 2.0 * obj.rd, 1)


class RatingHistoryPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatingHistory
        fields = (
            "event",
            "match",
            "mu_before",
            "mu_after",
            "rd_before",
            "rd_after",
            "delta",
            "applied_utc",
        )


class PlayerDetailSerializer(serializers.ModelSerializer):
    ratings = serializers.SerializerMethodField()
    records = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = (
            "player_id",
            "name_display",
            "first_name",
            "last_name",
            "country_code",
            "avatar_url",
            "dob",
            "height_cm",
            "plays",
            "gender",
            "ratings",
            "records",
        )

    def get_ratings(self, obj):
        qs = obj.ratings.all().order_by("-mu")
        return PlayerRatingSerializer(qs, many=True).data

    def get_records(self, obj):
        """Win/loss per discipline, computed from the lineup + winner side."""
        from django.db.models import Case, Count, F, IntegerField, Q, Sum, When

        rows = (
            MatchPlayer.objects.filter(player=obj)
            .values("match__event")
            .annotate(
                matches=Count("id"),
                wins=Sum(
                    Case(
                        When(side=F("match__winner_side"), then=1),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by("-matches")
        )
        return [
            {
                "event": r["match__event"],
                "matches": r["matches"],
                "wins": r["wins"] or 0,
                "losses": r["matches"] - (r["wins"] or 0),
            }
            for r in rows
        ]


class TournamentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = ("tournament_id", "name", "category_name", "start_date", "end_date")


class TournamentListSerializer(serializers.ModelSerializer):
    match_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "tournament_id",
            "name",
            "category_name",
            "start_date",
            "end_date",
            "venue_name",
            "prize_money",
            "match_count",
        )


class DrawBriefSerializer(serializers.Serializer):
    def to_representation(self, draw):
        return {
            "draw_value": draw.draw_value,
            "event": draw.event,
            "stage": draw.stage,
            "size": draw.size,
        }


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ("game_no", "side1_points", "side2_points")


class MatchLineupSerializer(serializers.ModelSerializer):
    player = PlayerBriefSerializer(read_only=True)

    class Meta:
        model = MatchPlayer
        fields = ("side", "player")


class MatchSerializer(serializers.ModelSerializer):
    tournament = TournamentBriefSerializer(read_only=True)
    lineup = MatchLineupSerializer(many=True, read_only=True)
    games = GameSerializer(many=True, read_only=True)
    elo = serializers.SerializerMethodField()
    team_elo = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            "match_id",
            "event",
            "round_name",
            "round_order",
            "match_time_utc",
            "duration_min",
            "score_status",
            "winner_side",
            "scoring_format",
            "rating_excluded",
            "tournament",
            "lineup",
            "games",
            "elo",
            "team_elo",
        )

    def _history(self, obj):
        return {
            h.player_id: (h.mu_before, h.mu_after, h.delta)
            for h in RatingHistory.objects.filter(match_id=obj.match_id)
        }

    def get_elo(self, obj):
        """Per-player rating for this match: {player_id: {before, after, delta}}.

        `before` is the player's rating at the START of this tournament (the
        locked figure the result is computed against), so the gain is legible.
        """
        return {
            pid: {"before": round(b), "after": round(a), "delta": round(d, 1)}
            for pid, (b, a, d) in self._history(obj).items()
        }

    def get_team_elo(self, obj):
        """Per-SIDE combined rating: {side: {before, after, delta}} — the PAIR's
        ELO for doubles (mean of members), the individual's for singles."""
        hist = self._history(obj)
        out = {}
        for side in (1, 2):
            vals = [
                hist[l.player_id]
                for l in obj.lineup.all()
                if l.side == side and l.player_id in hist
            ]
            if not vals:
                continue
            before = sum(v[0] for v in vals) / len(vals)
            after = sum(v[1] for v in vals) / len(vals)
            out[side] = {
                "before": round(before),
                "after": round(after),
                "delta": round(after - before, 1),
            }
        return out


class TournamentPerformanceSerializer(serializers.ModelSerializer):
    player = PlayerBriefSerializer(read_only=True)
    partner = PlayerBriefSerializer(read_only=True)
    tournament = TournamentBriefSerializer(read_only=True)

    class Meta:
        model = TournamentPerformance
        fields = (
            "player",
            "partner",
            "event",
            "tournament",
            "net_delta",
            "matches",
            "mu_start",
            "mu_end",
            "rd_start",
            "best_match",
            "best_delta",
        )


class MatchListSerializer(serializers.Serializer):
    """Compact match row for tournament/draw listings (both sides + score)."""

    def to_representation(self, m):
        lineup = list(m.lineup.all())
        games = [
            (g.side1_points, g.side2_points)
            for g in sorted(m.games.all(), key=lambda g: g.game_no)
        ]
        return {
            "match_id": m.match_id,
            "event": m.event,
            "round_name": m.round_name,
            "round_order": m.round_order,
            "match_time_utc": m.match_time_utc,
            "winner_side": m.winner_side,
            "score_status": m.score_status,
            "side1": PlayerBriefSerializer(
                [l.player for l in lineup if l.side == 1], many=True
            ).data,
            "side2": PlayerBriefSerializer(
                [l.player for l in lineup if l.side == 2], many=True
            ).data,
            "score": games,
        }


class PlayerMatchSerializer(serializers.Serializer):
    """One match from a given player's perspective (result + ELO gained)."""

    def to_representation(self, mp):
        m = mp.match
        deltas = self.context.get("deltas", {})
        lineup = list(m.lineup.all())
        partners = [
            l.player for l in lineup if l.side == mp.side and l.player_id != mp.player_id
        ]
        opponents = [l.player for l in lineup if l.side != mp.side]
        games = [
            (g.side1_points, g.side2_points)
            for g in sorted(m.games.all(), key=lambda g: g.game_no)
        ]
        if mp.side == 2:  # orient the score to the player's side
            games = [(b, a) for a, b in games]
        return {
            "match_id": m.match_id,
            "event": m.event,
            "round_name": m.round_name,
            "match_time_utc": m.match_time_utc,
            "score_status": m.score_status,
            "won": m.winner_side == mp.side,
            "tournament": TournamentBriefSerializer(m.tournament).data
            if m.tournament_id
            else None,
            "partners": PlayerBriefSerializer(partners, many=True).data,
            "opponents": PlayerBriefSerializer(opponents, many=True).data,
            "score": games,
            "elo": deltas.get(m.match_id),  # {before, after, delta} or None
            "elo_delta": (deltas.get(m.match_id) or {}).get("delta"),
        }
