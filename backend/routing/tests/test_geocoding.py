"""ORS-first geocoding with the Nominatim fallback (and the fallback client).

Hermetic: every test patches requests at module level; no network.
Cache isolation comes from the autouse fixture in tests/conftest.py.
"""

import pytest
from django.urls import reverse

from routing.services import geocoding, nominatim, ors
from routing.services.ors import RateLimitError, UpstreamError

_NOMINATIM_BODY = [
    {"display_name": "Amarillo, Potter County, Texas, USA", "lat": "35.222", "lon": "-101.8313"},
    {"display_name": "Amarillo,Randall County, Texas, USA", "lat": "35.1", "lon": "-101.9"},
]


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


# --- Facade: ORS first, Nominatim on failure ---------------------------------


def test_ors_success_skips_fallback(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("fallback must not run when ORS succeeds")

    monkeypatch.setattr(ors, "geocode", lambda text, size=5: [{"name": "ORS hit"}])
    monkeypatch.setattr(nominatim, "geocode", explode)

    assert geocoding.geocode("dal") == [{"name": "ORS hit"}]


def test_ors_quota_failure_falls_back_to_nominatim(monkeypatch):
    def quota_dead(text, size=5):
        raise UpstreamError("Geocoding service rejected the request.")

    monkeypatch.setattr(ors, "geocode", quota_dead)
    monkeypatch.setattr(
        nominatim, "geocode", lambda text, size=5: [{"name": "Nominatim hit"}]
    )

    assert geocoding.geocode("dal") == [{"name": "Nominatim hit"}]


def test_ors_rate_limit_falls_back_to_nominatim(monkeypatch):
    def limited(text, size=5):
        raise RateLimitError("Geocoding rate limit hit — try again shortly.")

    monkeypatch.setattr(ors, "geocode", limited)
    monkeypatch.setattr(
        nominatim, "geocode", lambda text, size=5: [{"name": "Nominatim hit"}]
    )

    assert geocoding.geocode("dal") == [{"name": "Nominatim hit"}]


def test_both_providers_failing_raises_upstream_error(monkeypatch):
    def dead(text, size=5):
        raise UpstreamError("Geocoding service is unreachable.")

    monkeypatch.setattr(ors, "geocode", dead)
    monkeypatch.setattr(nominatim, "geocode", dead)

    with pytest.raises(UpstreamError):
        geocoding.geocode("dal")


# --- Nominatim client --------------------------------------------------------


def test_nominatim_parses_places_and_drops_malformed(monkeypatch):
    payload = _NOMINATIM_BODY + [{"display_name": "no coords"}, {"lat": "1", "lon": "2"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        assert "nominatim.openstreetmap.org" in url
        assert headers.get("User-Agent")  # usage policy: identify the app
        return FakeResponse(200, payload)

    monkeypatch.setattr(nominatim.requests, "get", fake_get)

    results = nominatim.geocode("amarillo")

    assert results == [
        {"name": "Amarillo, Potter County, Texas, USA", "lat": 35.222, "lng": -101.8313},
        {"name": "Amarillo,Randall County, Texas, USA", "lat": 35.1, "lng": -101.9},
    ]


def test_nominatim_cached_second_call_hits_no_http(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(1)
        return FakeResponse(200, _NOMINATIM_BODY)

    monkeypatch.setattr(nominatim.requests, "get", fake_get)

    nominatim.geocode("amarillo")
    nominatim.geocode("amarillo")

    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(403, {"error": "Quota exceeded"}),
        FakeResponse(500, {}),
        FakeResponse(200, "not-a-list"),
    ],
)
def test_nominatim_failures_raise_upstream_error(monkeypatch, response):
    monkeypatch.setattr(
        nominatim.requests, "get", lambda *a, **k: response
    )

    with pytest.raises(UpstreamError):
        nominatim.geocode("dal")


def test_nominatim_rate_limit_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(
        nominatim.requests, "get", lambda *a, **k: FakeResponse(429, {})
    )

    with pytest.raises(RateLimitError):
        nominatim.geocode("dal")


def test_nominatim_network_error_raises_upstream_error(monkeypatch):
    def boom(*a, **k):
        raise nominatim.requests.RequestException("dns fail")

    monkeypatch.setattr(nominatim.requests, "get", boom)

    with pytest.raises(UpstreamError):
        nominatim.geocode("dal")


# --- Endpoint: the view survives a quota-dead ORS ----------------------------


@pytest.mark.django_db
def test_geocode_endpoint_serves_nominatim_when_ors_quota_dead(client, monkeypatch):
    def quota_dead(text, size=5):
        raise UpstreamError("Geocoding service rejected the request.")

    monkeypatch.setattr(ors, "geocode", quota_dead)

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(200, _NOMINATIM_BODY)

    monkeypatch.setattr(nominatim.requests, "get", fake_get)

    response = client.get(reverse("geocode"), {"text": "amarillo"})

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["name"].startswith("Amarillo")
    assert body["results"][0]["lat"] == 35.222
