"""Admin registrations — the Phase-1 data browser (PRD §5).

Every ingested model is registered so a `scrape` run can be inspected without
any custom tooling. Inlines let you read a match's lineup and games in one page.
"""
from django.contrib import admin

from .models import (
    Draw,
    Game,
    Match,
    MatchPlayer,
    MatchStatistics,
    Partnership,
    Player,
    PlayerRating,
    PlayerSeedRank,
    RatingHistory,
    RawCache,
    Tournament,
)

admin.site.register(MatchStatistics)
admin.site.register(PlayerSeedRank)


@admin.register(Partnership)
class PartnershipAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "player1",
        "player2",
        "combined_mu",
        "matches_together",
        "wins_together",
    )
    list_filter = ("event",)
    search_fields = ("player1__name_display", "player2__name_display")


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "tournament_id",
        "name",
        "category_name",
        "start_date",
        "end_date",
    )
    search_fields = ("name", "code", "venue_name")
    list_filter = ("category_name",)
    date_hierarchy = "start_date"


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("player_id", "name_display", "country_code", "plays")
    search_fields = ("name_display", "first_name", "last_name", "name_short")
    list_filter = ("country_code",)


@admin.register(Draw)
class DrawAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament", "event", "stage", "doubles", "size")
    list_filter = ("event", "stage", "doubles")
    search_fields = ("tournament__name",)


class MatchPlayerInline(admin.TabularInline):
    model = MatchPlayer
    extra = 0
    autocomplete_fields = ("player",)


class GameInline(admin.TabularInline):
    model = Game
    extra = 0


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "match_id",
        "tournament",
        "event",
        "round_name",
        "winner_side",
        "score_status",
        "scoring_format",
        "rating_excluded",
        "match_time_utc",
    )
    list_filter = ("event", "round_name", "score_status", "rating_excluded")
    search_fields = ("match_id", "code", "tournament__name")
    date_hierarchy = "match_time_utc"
    inlines = (MatchPlayerInline, GameInline)


@admin.register(MatchPlayer)
class MatchPlayerAdmin(admin.ModelAdmin):
    list_display = ("match", "side", "player")
    search_fields = ("match__match_id", "player__name_display")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("match", "game_no", "side1_points", "side2_points")


@admin.register(PlayerRating)
class PlayerRatingAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "event",
        "mu",
        "rd",
        "sigma",
        "matches_played",
        "last_match_utc",
    )
    list_filter = ("event",)
    search_fields = ("player__name_display",)


@admin.register(RatingHistory)
class RatingHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "event",
        "match",
        "mu_before",
        "mu_after",
        "delta",
        "applied_utc",
    )
    list_filter = ("event",)
    search_fields = ("player__name_display", "match__match_id")


@admin.register(RawCache)
class RawCacheAdmin(admin.ModelAdmin):
    list_display = ("url", "status", "fetched_utc")
    search_fields = ("url",)
    readonly_fields = ("url", "fetched_utc", "status", "body")
