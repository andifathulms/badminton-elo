"""API URL routes (PRD §12)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EventsView,
    LeaderboardView,
    MatchViewSet,
    PlayerViewSet,
)

# No trailing slash — cleaner URLs for the React/JSON client.
router = DefaultRouter(trailing_slash=False)
router.register("players", PlayerViewSet, basename="player")
router.register("matches", MatchViewSet, basename="match")

urlpatterns = [
    path("leaderboard", LeaderboardView.as_view(), name="leaderboard"),
    path("events", EventsView.as_view(), name="events"),
    path("", include(router.urls)),
]
