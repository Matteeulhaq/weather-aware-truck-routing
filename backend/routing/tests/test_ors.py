"""ORS client behavior against mocked HTTP responses."""

import pytest
import requests

from routing.services import ors
from routing.services.ors import RateLimitError, UpstreamError


def _directions_body(n_features=2):
    features = []
    for i in range(n_features):
        features.append(
            {
                "type": "Feature",
                "geometry": {"coordinates": [[-96.8, 32.77], [-101.8, 35.22]]},
                "properties": {
                    "summary": {"distance": 364000.0 + i, "duration": 20900.0 + i},
                    "segments": [
                        {"steps": [{"duration": 20900.0 + i, "way_points": [0, 1]}]}
                    ],
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


def test_get_directions_parses_features_and_sends_alternatives(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers, timeout=timeout)
        return FakeResponse(200, _directions_body(3))

    monkeypatch.setattr(ors.requests, "post", fake_post)

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 3
    assert "alternative_routes" in captured["body"]
    assert captured["body"]["alternative_routes"]["target_count"] == ors.MAX_ALTERNATIVES
    assert captured["body"]["coordinates"] == [[-96.8, 32.77], [-101.8, 35.22]]
    assert captured["body"]["geometry_simplify"] is False
    assert captured["body"]["instructions"] is True
    assert captured["headers"]["Authorization"]  # api key header present
    assert captured["timeout"] == ors.TIMEOUT_S


def test_get_directions_one_route_is_valid(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(200, _directions_body(1)))

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 1


def test_get_directions_429_raises_rate_limit(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(429, {}))

    with pytest.raises(RateLimitError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_get_directions_500_raises_upstream(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(500, {}))

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_get_directions_network_error_raises_upstream(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(ors.requests, "post", boom)

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_get_directions_empty_features_raises(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(200, {"features": []}))

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def _geocode_body():
    return {
        "features": [
            {"geometry": {"coordinates": [-96.797, 32.7767]}, "properties": {"label": "Dallas, TX"}},
            {"geometry": {"coordinates": [-101.8313, 35.222]}, "properties": {"label": "Amarillo, TX"}},
            {"geometry": {"coordinates": [None, None]}, "properties": {"label": "broken"}},  # skipped
        ]
    }


def test_geocode_parses_and_skips_malformed(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(params=params, timeout=timeout)
        return FakeResponse(200, _geocode_body())

    monkeypatch.setattr(ors.requests, "get", fake_get)

    results = ors.geocode("dal")

    assert results == [
        {"name": "Dallas, TX", "lng": -96.797, "lat": 32.7767},
        {"name": "Amarillo, TX", "lng": -101.8313, "lat": 35.222},
    ]
    assert captured["params"]["text"] == "dal"


def test_geocode_429_raises_rate_limit(monkeypatch):
    monkeypatch.setattr(ors.requests, "get", lambda *a, **k: FakeResponse(429, {}))

    with pytest.raises(RateLimitError):
        ors.geocode("dal")
