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
    assert captured["body"]["radiuses"] == [-1, -1]  # unlimited snapping
    assert captured["headers"]["Authorization"]  # api key header present
    assert captured["timeout"] == ors.TIMEOUT_S


def test_get_directions_one_route_is_valid(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(200, _directions_body(1)))

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 1


def test_long_route_falls_back_to_via_point_routes(monkeypatch):
    """Alternatives algorithm rejects >100 km pairs; direct + 2 via routes returned."""
    bodies = []

    def fake_post(url, json=None, headers=None, timeout=None):
        bodies.append(json)
        if json.get("alternative_routes"):
            return FakeResponse(
                400,
                {"error": {"code": 2004, "message": "approximated route distance must not be greater"}},
            )
        coords = json["coordinates"]
        if len(coords) == 3:
            detour_distance = 450_000.0 if coords[1][0] < -99.0 else 465_000.0  # two distinct corridors
        else:
            detour_distance = 410_000.0
        feature = _directions_body(1)["features"][0]
        feature["properties"]["summary"]["distance"] = detour_distance
        return FakeResponse(200, {"features": [feature]})

    monkeypatch.setattr(ors.requests, "post", fake_post)

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 3
    # First retry is the plain direct route (no alternatives key, 2 coords).
    assert bodies[1].get("alternative_routes") is None
    assert len(bodies[1]["coordinates"]) == 2
    # Then two via-point routes with 3 coordinates.
    assert len(bodies[2]["coordinates"]) == 3
    assert len(bodies[3]["coordinates"]) == 3
    # Direct route comes first.
    assert features[0]["properties"]["summary"]["distance"] == 410_000.0


def test_via_routes_failing_still_returns_direct(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        if json.get("alternative_routes"):
            return FakeResponse(400, {"error": {"code": 2004}})
        if len(json["coordinates"]) == 3:
            return FakeResponse(400, {"error": {"code": 2010, "message": "via point unroutable"}})
        return FakeResponse(200, _directions_body(1))

    monkeypatch.setattr(ors.requests, "post", fake_post)

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 1


def test_via_routes_duplicates_are_dropped(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        if json.get("alternative_routes"):
            return FakeResponse(400, {"error": {"code": 2004}})
        distance = 410_000.0  # all three come back "identical"
        feature = _directions_body(1)["features"][0]
        feature["properties"]["summary"]["distance"] = distance
        return FakeResponse(200, {"features": [feature]})

    monkeypatch.setattr(ors.requests, "post", fake_post)

    features = ors.get_directions((-96.8, 32.77), (-101.8, 35.22))

    assert len(features) == 1


def test_unroutable_pair_raises_upstream(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse(400, {"error": {"code": 2010, "message": "point not found"}})

    monkeypatch.setattr(ors.requests, "post", fake_post)

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_get_directions_429_raises_rate_limit(monkeypatch):
    monkeypatch.setattr(ors.requests, "post", lambda *a, **k: FakeResponse(429, {}))

    with pytest.raises(RateLimitError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_get_directions_network_error_raises_upstream(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(ors.requests, "post", boom)

    with pytest.raises(UpstreamError):
        ors.get_directions((-96.8, 32.77), (-101.8, 35.22))


def test_via_points_offset_perpendicular():
    # East-west line: offsets push off-route lat, vias flank opposite sides.
    vias = ors._via_points((-100.0, 35.0), (-95.0, 35.0))

    assert len(vias) == 2
    lng1, lat1 = vias[0]
    lng2, lat2 = vias[1]
    assert 35.0 < lat1 < 36.0  # north corridor
    assert 34.0 < lat2 < 35.0  # south corridor
    assert -100.0 < lng1 < -95.0 and -100.0 < lng2 < -95.0  # both along the route


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
