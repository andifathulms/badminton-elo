"""Root URL configuration.

Admin is the Phase-1 inspection UI; the DRF read API (apps.api) serves the
leaderboard/player/match endpoints for the React frontend (Phase 3).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
]
