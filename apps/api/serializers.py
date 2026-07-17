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
    Partnership,
    Player,
    PlayerRating,
    RatingHistory,
    Tournament,
)


class PlayerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ("player_id", "name_display", "country_code", "avatar_url")


class PairSerializer(serializers.ModelSerializer):
    player1 = PlayerBriefSerializer(read_only=True)
    player2 = PlayerBriefSerializer(read_only=True)
    rating = serializers.SerializerMethodField()
    win_pct = serializers.SerializerMethodField()

    class Meta:
        model = Partnership
        fields = (
            "event",
            "player1",
            "player2",
            "rating",
            "combined_mu",
            "combined_rd",
            "matches_together",
            "wins_together",
            "win_pct",
            "last_match_utc",
        )

    def get_rating(self, obj) -> float:
        return round(obj.combined_mu - 2.0 * obj.combined_rd, 1)

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
            "ratings",
        )

    def get_ratings(self, obj):
        qs = obj.ratings.all().order_by("-mu")
        return PlayerRatingSerializer(qs, many=True).data


class TournamentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = ("tournament_id", "name", "category_name", "start_date", "end_date")


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
        )

    def get_elo(self, obj):
        """Per-player rating change from this match: {player_id: delta}."""
        return {
            h.player_id: round(h.delta, 1)
            for h in RatingHistory.objects.filter(match_id=obj.match_id)
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
            "elo_delta": deltas.get(m.match_id),
        }
