"""API URL routes (PRD §12)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyticsView,
    CupView,
    EventsView,
    LeaderboardView,
    MatchViewSet,
    PairDetailView,
    PairsView,
    PerformancePathView,
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
    path("pairs/detail", PairDetailView.as_view(), name="pair-detail"),
    path("pairs", PairsView.as_view(), name="pairs"),
    path("analytics/<str:kind>", AnalyticsView.as_view(), name="analytics"),
    path("cups/<str:cup>", CupView.as_view(), name="cups"),
    path("performance/path", PerformancePathView.as_view(), name="performance-path"),
    path("events", EventsView.as_view(), name="events"),
    path(
        "players/<int:player_id>/matches",
        PlayerMatchesView.as_view(),
        name="player-matches",
    ),
    path("", include(router.urls)),
]
