"""API URL routes (PRD §12)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EventsView,
    LeaderboardView,
    MatchViewSet,
    PairsView,
    PlayerMatchesView,
    PlayerViewSet,
    TournamentViewSet,
)

# No trailing slash — cleaner URLs for the React/JSON client.
router = DefaultRouter(trailing_slash=False)
router.register("players", PlayerViewSet, basename="player")
router.register("matches", MatchViewSet, basename="match")
router.register("tournaments", TournamentViewSet, basename="tournament")

urlpatterns = [
    path("leaderboard", LeaderboardView.as_view(), name="leaderboard"),
    path("pairs", PairsView.as_view(), name="pairs"),
    path("events", EventsView.as_view(), name="events"),
    path(
        "players/<int:player_id>/matches",
        PlayerMatchesView.as_view(),
        name="player-matches",
    ),
    path("", include(router.urls)),
]
