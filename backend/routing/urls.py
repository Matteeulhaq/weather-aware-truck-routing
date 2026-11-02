from django.urls import path

from .views import geocode, health, plan

urlpatterns = [
    path("health/", health, name="health"),
    path("geocode/", geocode, name="geocode"),
    path("plan/", plan, name="plan"),
]
