"""API URL routes (PRD §12)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import reconcile

from .views import (
    AgingView,
    AnalyticsView,
    CalibrationView,
    ClutchView,
    ConsistencyView,
    CupHistoryView,
    DynastiesView,
    CupView,
    EventsView,
    H2HView,
    LeaderboardView,
    MatchViewSet,
    PairDetailView,
    PairsView,
    PerformancePathView,
    PlayerMatchesView,
    PlayerViewSet,
    RecordsView,
    SynergyView,
    TournamentViewSet,
)

# No trailing slash — cleaner URLs for the React/JSON client.
router = DefaultRouter(trailing_slash=False)
router.register("players", PlayerViewSet, basename="player")
router.register("matches", MatchViewSet, basename="match")
router.register("tournaments", TournamentViewSet, basename="tournament")

urlpatterns = [
    path("leaderboard", LeaderboardView.as_view(), name="leaderboard"),
    path("h2h", H2HView.as_view(), name="h2h"),
    path("pairs/detail", PairDetailView.as_view(), name="pair-detail"),
    path("pairs", PairsView.as_view(), name="pairs"),
    path("analytics/calibration", CalibrationView.as_view(), name="calibration"),
    path("analytics/aging", AgingView.as_view(), name="aging"),
    path("analytics/clutch", ClutchView.as_view(), name="clutch"),
    path("analytics/dynasties", DynastiesView.as_view(), name="dynasties"),
    path("analytics/consistency", ConsistencyView.as_view(), name="consistency"),
    path("analytics/synergy", SynergyView.as_view(), name="synergy"),
    path("analytics/<str:kind>", AnalyticsView.as_view(), name="analytics"),
    path("cups/<str:cup>/history", CupHistoryView.as_view(), name="cup-history"),
    path("cups/<str:cup>", CupView.as_view(), name="cups"),
    path("performance/path", PerformancePathView.as_view(), name="performance-path"),
    path("records/<str:kind>", RecordsView.as_view(), name="records"),
    path("reconcile/cases", reconcile.cases, name="reconcile-cases"),
    path("reconcile/decide", reconcile.decide, name="reconcile-decide"),
    path("reconcile/merge-all-single", reconcile.merge_all_single, name="reconcile-merge-all"),
    path("events", EventsView.as_view(), name="events"),
    path(
        "players/<int:player_id>/matches",
        PlayerMatchesView.as_view(),
        name="player-matches",
    ),
    path("", include(router.urls)),
]
