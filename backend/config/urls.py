"""
URL configuration for the Weather-Aware Truck Routing app.
"""

from django.urls import include, path

urlpatterns = [
    path("api/", include("routing.urls")),
]
