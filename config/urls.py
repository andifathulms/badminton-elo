"""Root URL configuration.

Admin is the Phase-1 inspection UI; the DRF read API (apps.api) serves the
leaderboard/player/match endpoints. For a single-process local demo, Django can
also serve the built React app (frontend/dist) so the whole site runs on ONE
port — `python manage.py runserver`, no separate Vite server. In Docker/prod the
frontend is served by its own nginx container and these SPA routes go unused.
"""
from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

from apps.api import reconcile

DIST = settings.BASE_DIR / "frontend" / "dist"


def spa(request, *args, **kwargs):
    """Serve the built SPA shell; React Router handles the client-side route."""
    index = DIST / "index.html"
    if not index.exists():
        raise Http404("frontend not built — run `npm run build` in frontend/")
    return FileResponse(open(index, "rb"))


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
    path("reconcile/", reconcile.page, name="reconcile-page"),
    # Built frontend assets (JS/CSS/images) live under dist/assets.
    re_path(r"^assets/(?P<path>.*)$", static_serve, {"document_root": DIST / "assets"}),
    # Catch-all: any non-API path returns the SPA shell so deep links / refreshes
    # work. Must stay last, and must not shadow api/admin/reconcile/assets.
    re_path(r"^(?!api/|admin/|reconcile/|assets/|static/).*$", spa),
]
