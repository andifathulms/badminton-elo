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
    Player,
    PlayerRating,
    RatingHistory,
    Tournament,
)


class PlayerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ("player_id", "name_display", "country_code", "avatar_url")


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
        )
