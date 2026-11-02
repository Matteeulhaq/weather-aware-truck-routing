"""Request validation for the planning API.

`origin`/`destination` accept either a free-text place (backend geocodes it,
first hit) or a resolved place object from the autocomplete picker
({"name", "lat", "lng"}) — the latter avoids geocode drift.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .services import ors

MAX_LOAD_LBS = 80_000
# Small tolerance so a client clock a few minutes behind doesn't get rejected.
_PAST_TOLERANCE = timedelta(minutes=5)


class PlaceField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, str):
            name = data.strip()
            if not name:
                raise serializers.ValidationError("Place name must not be empty.")
            return {"name": name, "lat": None, "lng": None}

        if isinstance(data, dict):
            name = data.get("name")
            lat, lng = data.get("lat"), data.get("lng")
            if not isinstance(name, str) or not name.strip():
                raise serializers.ValidationError("Place 'name' must be a non-empty string.")
            try:
                lat, lng = float(lat), float(lng)
            except (TypeError, ValueError):
                raise serializers.ValidationError("Place requires numeric 'lat' and 'lng'.")
            if not (-90 <= lat <= 90):
                raise serializers.ValidationError("'lat' out of range.")
            if not (-180 <= lng <= 180):
                raise serializers.ValidationError("'lng' out of range.")
            return {"name": name.strip(), "lat": lat, "lng": lng}

        raise serializers.ValidationError("Place must be a string or {name, lat, lng}.")


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure_time = serializers.DateTimeField()
    load_weight_lbs = serializers.IntegerField(min_value=1, max_value=MAX_LOAD_LBS)
    sample_interval_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate_departure_time(self, value):
        # DateTimeField with USE_TZ returns an aware datetime in UTC.
        if value < timezone.now() - _PAST_TOLERANCE:
            raise serializers.ValidationError("Departure time is in the past.")
        return value


def resolve_place(place: dict) -> dict:
    """Fill in coordinates for a free-text place via geocoding (first hit)."""
    if place["lat"] is not None:
        return place
    results = ors.geocode(place["name"], size=1)
    if not results:
        raise LookupError(f"Could not find '{place['name']}'.")
    return results[0]
