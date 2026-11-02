"""Open-Meteo client behavior against mocked HTTP responses."""

import pytest

from routing.services import open_meteo as om
from routing.services.open_meteo import UpstreamError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _hourly_entry(hours=72, base_epoch=1_760_000_000):
    return {
        "hourly": {
            "time": [base_epoch + i * 3600 for i in range(hours)],
            "wind_speed_10m": [10.0 + i for i in range(hours)],
            "rain": [0.0] * hours,
            "snowfall": [0.1] * hours,
        }
    }


def test_multi_location_returns_array_in_input_order(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(params=params, timeout=timeout)
        return FakeResponse(200, [_hourly_entry(), _hourly_entry()])

    monkeypatch.setattr(om.requests, "get", fake_get)

    results = om.get_hourly_forecasts([(35.0, -100.0), (32.0, -96.0)])

    assert len(results) == 2
    assert captured["params"]["latitude"] == "35.000000,32.000000"
    assert captured["params"]["longitude"] == "-100.000000,-96.000000"
    assert captured["params"]["wind_speed_unit"] == "mph"
    assert captured["params"]["precipitation_unit"] == "inch"
    assert captured["params"]["timeformat"] == "unixtime"
    assert captured["timeout"] == om.TIMEOUT_S


def test_single_location_object_is_wrapped(monkeypatch):
    monkeypatch.setattr(om.requests, "get", lambda *a, **k: FakeResponse(200, _hourly_entry()))

    results = om.get_hourly_forecasts([(35.0, -100.0)])

    assert len(results) == 1


def test_full_grid_returned_untruncated(monkeypatch):
    monkeypatch.setattr(om.requests, "get", lambda *a, **k: FakeResponse(200, _hourly_entry(hours=72)))

    results = om.get_hourly_forecasts([(35.0, -100.0)])

    series = results[0]
    for key in ("hours", "wind_mph", "rain_in_hr", "snow_in_hr"):
        assert len(series[key]) == 72  # planner slices the departure-relative window


def test_batches_150_points_into_two_requests(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        n = len(params["latitude"].split(","))
        return FakeResponse(200, [_hourly_entry() for _ in range(n)])

    monkeypatch.setattr(om.requests, "get", fake_get)

    points = [(35.0 + i * 0.01, -100.0) for i in range(150)]
    results = om.get_hourly_forecasts(points)

    assert len(calls) == 2
    assert len(calls[0]["latitude"].split(",")) == 100
    assert len(calls[1]["latitude"].split(",")) == 50
    assert len(results) == 150


def test_null_values_preserved_as_none(monkeypatch):
    entry = _hourly_entry(hours=72)
    entry["hourly"]["snowfall"][5] = None
    monkeypatch.setattr(om.requests, "get", lambda *a, **k: FakeResponse(200, entry))

    results = om.get_hourly_forecasts([(35.0, -100.0)])

    assert results[0]["snow_in_hr"][5] is None


def test_error_status_raises_upstream(monkeypatch):
    monkeypatch.setattr(om.requests, "get", lambda *a, **k: FakeResponse(500, {}))

    with pytest.raises(UpstreamError):
        om.get_hourly_forecasts([(35.0, -100.0)])


def test_empty_points_returns_empty(monkeypatch):
    assert om.get_hourly_forecasts([]) == []
