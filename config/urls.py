"""Root URL configuration.

Phase 1 exposes only the Django admin — the inspection UI for ingested data.
DRF viewsets (apps.api) are wired in during Phase 3.
"""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
