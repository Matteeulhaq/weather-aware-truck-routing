"""Plan request validation and the geocode endpoint."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from routing.serializers import PlanRequestSerializer
from routing.services.ors import UpstreamError


def _payload(**overrides):
    base = {
        "origin": "Dallas, TX",
        "destination": {"name": "Amarillo, TX", "lat": 35.222, "lng": -101.8313},
        "departure_time": (timezone.now() + timedelta(hours=12)).isoformat(),
        "load_weight_lbs": 35_000,
        "sample_interval_miles": 25,
    }
    base.update(overrides)
    return base


def test_serializer_accepts_mixed_place_forms():
    serializer = PlanRequestSerializer(data=_payload())

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["origin"]["lat"] is None  # geocode later
    assert serializer.validated_data["destination"]["lat"] == 35.222


def test_serializer_rejects_overweight_load():
    serializer = PlanRequestSerializer(data=_payload(load_weight_lbs=90_000))

    assert not serializer.is_valid()
    assert "load_weight_lbs" in serializer.errors


def test_serializer_rejects_bad_interval():
    serializer = PlanRequestSerializer(data=_payload(sample_interval_miles=15))

    assert not serializer.is_valid()
    assert "sample_interval_miles" in serializer.errors


def test_serializer_rejects_past_departure():
    past = (timezone.now() - timedelta(hours=1)).isoformat()

    serializer = PlanRequestSerializer(data=_payload(departure_time=past))

    assert not serializer.is_valid()
    assert "departure_time" in serializer.errors


def test_serializer_rejects_bad_coordinates():
    serializer = PlanRequestSerializer(data=_payload(destination={"name": "X", "lat": 200, "lng": 0}))

    assert not serializer.is_valid()


@pytest.mark.django_db
def test_geocode_returns_results(client, monkeypatch):
    from routing.views import geocode as geocode_view  # noqa: F401  (URL wiring smoke)
    from routing.services import ors

    monkeypatch.setattr(
        ors, "geocode",
        lambda text, size=5: [{"name": "Dallas, TX", "lng": -96.797, "lat": 32.7767}],
    )

    response = client.get(reverse("geocode"), {"text": "dal"})

    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "Dallas, TX"


@pytest.mark.django_db
def test_geocode_short_text_returns_empty(client):
    response = client.get(reverse("geocode"), {"text": "d"})

    assert response.status_code == 200
    assert response.json() == {"results": []}


@pytest.mark.django_db
def test_geocode_upstream_failure_maps_to_502(client, monkeypatch):
    from routing.services import ors

    def boom(text, size=5):
        raise UpstreamError("Geocoding service is unreachable.")

    monkeypatch.setattr(ors, "geocode", boom)

    response = client.get(reverse("geocode"), {"text": "dal"})

    assert response.status_code == 502
    assert "detail" in response.json()
