"""Caching and retry behavior of the ORS and Open-Meteo clients.

Cache isolation comes from the autouse fixture in tests/conftest.py.
"""

import pytest

from routing.services import open_meteo as om
from routing.services import ors
from routing.services.open_meteo import UpstreamError as WeatherUpstreamError
from routing.services.ors import UpstreamError


def _directions_body(n_features=1):
    features = []
    for i in range(n_features):
        features.append(
            {
                "type": "Feature",
                "geometry": {"coordinates": [[-96.8, 32.77], [-101.8, 35.22]]},
                "properties": {
                    "summary": {"distance": 364000.0 + i, "duration": 20900.0 + i},
                    "segments": [{"steps": [{"duration": 20900.0 + i, "way_points": [0, 1]}]}],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_directions_cached_second_call_hits_no_http(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(1)
        return FakeResponse(200, _directions_body(2))

    monkeypatch.setattr(ors.requests, "post", fake_post)

    first = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))
    second = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(calls) == 1  # second call served from cache
    assert first == second


def test_geocode_cached_second_call_hits_no_http(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return FakeResponse(200, {"features": [
            {"geometry": {"coordinates": [-96.797, 32.7767]}, "properties": {"label": "Dallas, TX"}},
        ]})

    monkeypatch.setattr(ors.requests, "get", fake_get)

    ors.geocode("dal")
    ors.geocode("dal")

    assert len(calls) == 1


def test_weather_cached_second_call_hits_no_http(monkeypatch):
    calls = []

    entry = {
        "hourly": {
            "time": [1_760_000_000 + i * 3600 for i in range(72)],
            "wind_speed_10m": [10.0] * 72,
            "rain": [0.0] * 72,
            "snowfall": [0.0] * 72,
        }
    }

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return FakeResponse(200, [entry, entry])

    monkeypatch.setattr(om.requests, "get", fake_get)

    points = [(35.0, -100.0), (35.2, -99.5)]
    first = om.get_hourly_forecasts(points)
    second = om.get_hourly_forecasts(points)

    assert len(calls) == 1
    assert first == second


def test_ors_retries_transient_5xx_then_succeeds(monkeypatch):
    attempts = []

    def fake_post(url, json=None, headers=None, timeout=None):
        attempts.append(json.get("alternative_routes") is not None)
        if len(attempts) == 1:
            return FakeResponse(503, {})
        return FakeResponse(200, _directions_body(1))

    monkeypatch.setattr(ors.requests, "post", fake_post)
    monkeypatch.setattr(ors.time, "sleep", lambda s: None)

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(attempts) == 2
    assert len(features) == 1


def test_ors_fails_after_two_transient_5xx(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(503, {}))
    monkeypatch.setattr(ors.time, "sleep", lambda s: None)

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_weather_retries_transient_5xx_then_succeeds(monkeypatch):
    attempts = []
    entry = {
        "hourly": {
            "time": [1_760_000_000 + i * 3600 for i in range(72)],
            "wind_speed_10m": [10.0] * 72,
            "rain": [0.0] * 72,
            "snowfall": [0.0] * 72,
        }
    }

    def fake_get(url, params=None, timeout=None):
        attempts.append(1)
        if len(attempts) == 1:
            return FakeResponse(502, {})
        return FakeResponse(200, entry)

    monkeypatch.setattr(om.requests, "get", fake_get)
    monkeypatch.setattr(om.time, "sleep", lambda s: None)

    results = om.get_hourly_forecasts([(35.0, -100.0)])

    assert len(attempts) == 2
    assert len(results) == 1


def test_weather_fails_after_two_transient_5xx(monkeypatch):
    monkeypatch.setattr(om.requests, "get", lambda *a, **k: FakeResponse(503, {}))
    monkeypatch.setattr(om.time, "sleep", lambda s: None)

    with pytest.raises(WeatherUpstreamError):
        om.get_hourly_forecasts([(35.0, -100.0)])
