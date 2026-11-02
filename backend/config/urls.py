"""
URL configuration for the Weather-Aware Truck Routing app.

API routes are explicit; everything else serves the single-page app built
from client/dist (collected into staticfiles/ at deploy time).
"""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.urls import include, path, re_path


def spa(request):
    """Serve the React app's index.html for any non-API path."""
    index = Path(settings.STATIC_ROOT) / "index.html"
    if not index.exists():
        return JsonResponse({"detail": "Frontend build not deployed."}, status=404)
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/", include("routing.urls")),
    re_path(r"^(?!api/|static/).*$", spa, name="spa"),
]
