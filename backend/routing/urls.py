from django.urls import path

from .views import geocode, health

urlpatterns = [
    path("health/", health, name="health"),
    path("geocode/", geocode, name="geocode"),
]
