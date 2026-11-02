"""End-to-end /api/plan/ tests with mocked ORS + Open-Meteo."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from routing.services import geocoding, open_meteo, ors

METERS_PER_MILE = 1609.344


def departure_epoch():
    """The epoch the request payload sends — mocks anchor their grid to it."""
    return int((timezone.now() + timedelta(hours=12)).timestamp())


def _feature(distance_m, duration_s):
    return {
        "type": "Feature",
        "geometry": {"coordinates": [[-96.8, 32.77], [-101.83, 35.22]]},
        "properties": {
            "summary": {"distance": distance_m, "duration": duration_s},
            "segments": [{"steps": [{"duration": duration_s, "way_points": [0, 1]}]}],
        },
    }


def _forecast(wind_mph):
    grid_start = departure_epoch() - 3600  # grid starts 1 h before departure
    hours = [grid_start + i * 3600 for i in range(72)]
    return {
        "hours": hours,
        "wind_mph": [wind_mph] * 72,
        "rain_in_hr": [0.0] * 72,
        "snow_in_hr": [0.0] * 72,
    }


@pytest.fixture
def patch_upstream(monkeypatch):
    """Two routes: same geometry, second one twice as slow; calm weather.

    Patches every upstream call the planner makes — geocode included — so
    the endpoint tests stay hermetic (CI has no ORS_API_KEY and must not
    need one).
    """

    def install(wind_mph=15.0):
        monkeypatch.setattr(geocoding, "geocode", lambda text, size=5: [
            {"name": "Dallas, TX", "lng": -96.8, "lat": 32.77}
        ])
        monkeypatch.setattr(ors, "get_directions", lambda *a, **k: [
            _feature(400_000, 14_400),  # ~249 mi, 4 h
            _feature(410_000, 28_800),  # ~255 mi, 8 h
        ])
        monkeypatch.setattr(
            open_meteo, "get_hourly_forecasts",
            lambda points: [_forecast(wind_mph) for _ in points],
        )

    return install


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


@pytest.mark.django_db
def test_plan_returns_full_analysis(client, patch_upstream):
    patch_upstream()

    response = client.post(reverse("plan"), _payload(), content_type="application/json")
    body = response.json()

    assert response.status_code == 200
    assert body["recommended_route_id"] in ("route_1", "route_2")
    assert sum(r["is_recommended"] for r in body["routes"]) == 1
    # Departure-relative hours window (<= 49 entries), starting at departure.
    assert 0 < len(body["hours"]) <= 49
    route = body["routes"][0]
    assert route["checkpoints"][0]["distance_miles"] == 0.0
    assert all("risk" in cp for cp in route["checkpoints"])


@pytest.mark.django_db
def test_plan_checkpoints_monotonic_and_anchored(client, patch_upstream):
    patch_upstream()

    body = client.post(reverse("plan"), _payload(), content_type="application/json").json()

    for route, total_m in zip(body["routes"], (400_000, 410_000)):
        cps = route["checkpoints"]
        assert all(b["distance_miles"] > a["distance_miles"] for a, b in zip(cps, cps[1:]))
        assert all(b["eta"] >= a["eta"] for a, b in zip(cps, cps[1:]))
        # Final checkpoint is the destination at that route's total distance.
        assert math_isclose(cps[-1]["distance_miles"], total_m / METERS_PER_MILE, rel_tol=0.01)


def math_isclose(a, b, rel_tol):
    return abs(a - b) <= rel_tol * max(abs(a), abs(b))


@pytest.mark.django_db
def test_plan_load_rule_escalates_severe_wind_with_heavy_load(client, patch_upstream):
    # 40 mph wind = High; >40,000 lb load escalates to Severe.
    patch_upstream(wind_mph=40.0)

    body = client.post(
        reverse("plan"), _payload(load_weight_lbs=45_000), content_type="application/json"
    ).json()

    for route in body["routes"]:
        for cp in route["checkpoints"]:
            assert cp["risk"]["wind"] == "High"
            assert cp["risk"]["overall"] == "Severe"
            assert "40,000" in cp["risk"]["load_rule_triggered"]


@pytest.mark.django_db
def test_plan_light_load_keeps_high_wind_at_high(client, patch_upstream):
    patch_upstream(wind_mph=40.0)

    body = client.post(
        reverse("plan"), _payload(load_weight_lbs=35_000), content_type="application/json"
    ).json()

    for cp in body["routes"][0]["checkpoints"]:
        assert cp["risk"]["overall"] == "High"
        assert cp["risk"]["load_rule_triggered"] is None


@pytest.mark.django_db
def test_plan_recommends_safest_route_when_weather_differs(client, patch_upstream, monkeypatch):
    """Storm (45 mph) on route 1, calm on route 2 -> route 2 wins on severe miles."""
    patch_upstream()

    def _route_point_counts():
        from routing.services.checkpoints import build_checkpoints

        counts = []
        for f in (_feature(400_000, 14_400), _feature(410_000, 28_800)):
            cps = build_checkpoints(
                coords=f["geometry"]["coordinates"],
                segments=f["properties"]["segments"],
                summary_distance_m=f["properties"]["summary"]["distance"],
                summary_duration_s=f["properties"]["summary"]["duration"],
                departure_epoch=departure_epoch(),
                interval_miles=25,
            )
            counts.append(len(cps))
        return counts

    def split_forecasts(points):
        counts = _route_point_counts()
        out = []
        for count, wind in zip(counts, (45.0, 10.0)):
            out.extend([_forecast(wind) for _ in range(count)])
        return out

    monkeypatch.setattr(open_meteo, "get_hourly_forecasts", split_forecasts)

    response = client.post(reverse("plan"), _payload(), content_type="application/json")
    body = response.json()

    assert response.status_code == 200
    assert body["recommended_route_id"] == "route_2"
    assert body["routes"][0]["summary"]["severe_miles"] > 0
    assert body["routes"][1]["summary"]["severe_miles"] == 0
    assert "severe" in body["recommendation_reason"].lower()


@pytest.mark.django_db
def test_plan_handles_horizon_gracefully(client, patch_upstream, monkeypatch):
    patch_upstream()
    # Only 2 forecast hours: most checkpoints fall beyond the grid.
    from routing.services import open_meteo as om

    def short_forecast(points):
        grid_start = departure_epoch() - 3600
        hours = [grid_start + i * 3600 for i in range(2)]
        return [
            {"hours": hours, "wind_mph": [15.0, 15.0], "rain_in_hr": [0.0, 0.0], "snow_in_hr": [0.0, 0.0]}
            for _ in points
        ]

    monkeypatch.setattr(om, "get_hourly_forecasts", short_forecast)

    response = client.post(reverse("plan"), _payload(), content_type="application/json")
    body = response.json()

    assert response.status_code == 200
    assert body["routes"]  # structure survives
    unavailable = [cp for cp in body["routes"][0]["checkpoints"] if not cp["weather"].get("available")]
    assert unavailable
    assert body["warnings"]
    assert any(cp["risk"] is None for cp in body["routes"][0]["checkpoints"])


@pytest.mark.django_db
def test_plan_geocode_miss_maps_to_400(client, monkeypatch):
    monkeypatch.setattr(geocoding, "geocode", lambda text, size=1: [])

    response = client.post(reverse("plan"), _payload(), content_type="application/json")

    assert response.status_code == 400
    assert "Could not find" in response.json()["detail"]


@pytest.mark.django_db
def test_plan_directions_failure_maps_to_502(client, patch_upstream, monkeypatch):
    patch_upstream()
    from routing.services.ors import UpstreamError

    def boom(*a, **k):
        raise UpstreamError("Routing service is unreachable.")

    monkeypatch.setattr(ors, "get_directions", boom)

    response = client.post(reverse("plan"), _payload(), content_type="application/json")

    assert response.status_code == 502
