"""End-to-end trip planning pipeline.

geocode → directions (up to 3 alternatives) → checkpoint interpolation →
batched weather → per-checkpoint risk → per-route stats → recommendation.

Response contract highlights (consumed by the React client):
- `hours` is the *departure-relative* UTC epoch grid (49 entries, 0–48 h) —
  the slider's time axis. Per-checkpoint `hourly.risk_scores` are aligned
  with it positionally, so the client never has to re-align or re-fetch.
- Each checkpoint's `risk` is the authoritative risk *at its ETA*; the
  `hourly` series exists only to drive the heatmap slider.
- Checkpoints whose ETA falls beyond the forecast horizon get
  `weather.available = false` and `risk = null`, and are surfaced in
  `warnings[]` — they are excluded from band mileage and averages upstream
  (see risk.aggregate.route_stats).
"""

import logging
from datetime import datetime, timezone as dt_timezone

from . import geocoding, open_meteo, ors
from .checkpoints import build_checkpoints
from ..risk.aggregate import CheckpointAssessment, recommend, route_stats
from ..risk.classify import checkpoint_risk
from ..risk.levels import RiskLevel

logger = logging.getLogger("routing")

SLIDER_HOURS = 48  # client window: 0..48 h after departure
SECONDS_PER_HOUR = 3600


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _hour_index(hours: list, epoch: int) -> int:
    """Index of `epoch` in an hourly epoch grid; -1 when out of range."""
    if not hours:
        return -1
    index = round((epoch - hours[0]) / SECONDS_PER_HOUR)
    if 0 <= index < len(hours):
        return index
    return -1


def _weather_at(forecast: dict, epoch: int) -> dict | None:
    """Weather values at the hour nearest `epoch`, or None beyond the grid."""
    index = _hour_index(forecast["hours"], epoch)
    if index < 0:
        return None
    wind = forecast["wind_mph"][index]
    rain = forecast["rain_in_hr"][index]
    snow = forecast["snow_in_hr"][index]
    if wind is None or rain is None or snow is None:
        return None
    return {
        "wind_mph": round(float(wind), 1),
        "rain_in_hr": round(float(rain), 2),
        "snow_in_hr": round(float(snow), 2),
        "available": True,
    }


def _resolve_place(place: dict) -> dict:
    """Coordinates for a free-text place (first geocode hit); passes through resolved ones."""
    if place["lat"] is not None:
        return place
    results = geocoding.geocode(place["name"], size=1)
    if not results:
        raise LookupError(f"Could not find '{place['name']}'.")
    return results[0]


def plan_trip(
    origin: dict,
    destination: dict,
    departure_epoch: int,
    load_lbs: int,
    interval_miles: float,
) -> dict:
    """Run the full pipeline and build the API response dict."""
    origin = _resolve_place(origin)
    destination = _resolve_place(destination)

    features = ors.get_directions(
        (origin["lng"], origin["lat"]),
        (destination["lng"], destination["lat"]),
    )

    # Checkpoints per route.
    route_checkpoints = []
    for feature in features:
        summary = feature["properties"]["summary"]
        route_checkpoints.append(
            build_checkpoints(
                coords=feature["geometry"]["coordinates"],
                segments=feature["properties"].get("segments"),
                summary_distance_m=summary["distance"],
                summary_duration_s=summary["duration"],
                departure_epoch=departure_epoch,
                interval_miles=interval_miles,
            )
        )

    # One batched weather fetch for every checkpoint of every route.
    all_points = [
        (cp["lat"], cp["lng"])
        for cps in route_checkpoints
        for cp in cps
    ]
    forecasts = open_meteo.get_hourly_forecasts(all_points)

    warnings = []
    routes = []
    stats_list = []

    cursor = 0  # index into the flat forecasts list
    for route_no, cps in enumerate(route_checkpoints, start=1):
        route_forecasts = forecasts[cursor : cursor + len(cps)]
        cursor += len(cps)

        assessments = []
        for cp, forecast in zip(cps, route_forecasts):
            weather = _weather_at(forecast, cp["eta_epoch"])
            if weather is None:
                risk = None
                warnings.append(
                    f"Route {route_no}: no forecast for checkpoint {cp['seq'] + 1} "
                    "(beyond the forecast horizon)."
                )
            else:
                risk = checkpoint_risk(
                    wind_mph=weather["wind_mph"],
                    rain_in_hr=weather["rain_in_hr"],
                    snow_in_hr=weather["snow_in_hr"],
                    load_lbs=load_lbs,
                )

            # Miles this checkpoint covers: its distance to the next checkpoint.
            seq = cp["seq"]
            coverage = 0.0
            if seq + 1 < len(cps):
                coverage = cps[seq + 1]["distance_miles"] - cp["distance_miles"]

            assessments.append(
                CheckpointAssessment(
                    seq=seq,
                    lat=cp["lat"],
                    lng=cp["lng"],
                    distance_miles=cp["distance_miles"],
                    eta_epoch=cp["eta_epoch"],
                    weather=weather or {},
                    risk=risk,
                    coverage_miles=coverage,
                )
            )

        summary_m = cps[-1]["distance_miles"]
        duration_h = cps[-1]["duration_hours"]
        stats = route_stats(assessments, distance_miles=summary_m, duration_hours=duration_h)
        stats_list.append(stats)

        # Departure-relative client window: slice [departure_idx : departure_idx + 49]
        # out of the full grid (planner-side truncation; open_meteo returns ~72 h).
        reference = route_forecasts[0]
        departure_idx = max(0, _hour_index(reference["hours"], departure_epoch))
        window = slice(departure_idx, departure_idx + SLIDER_HOURS + 1)

        checkpoints_json = []
        for assessment, forecast in zip(assessments, route_forecasts):
            eta_idx = _hour_index(forecast["hours"], assessment.eta_epoch)
            risk_scores = None
            if 0 <= departure_idx < len(forecast["hours"]):
                risk_scores = []
                for h in range(len(forecast["hours"][window])):
                    w = _weather_at(forecast, forecast["hours"][window][h])
                    risk_scores.append(
                        checkpoint_risk(w["wind_mph"], w["rain_in_hr"], w["snow_in_hr"], load_lbs).score
                        if w
                        else None
                    )

            checkpoints_json.append(
                {
                    "seq": assessment.seq,
                    "distance_miles": round(assessment.distance_miles, 1),
                    "eta": _iso(assessment.eta_epoch),
                    "lat": assessment.lat,
                    "lng": assessment.lng,
                    "weather": assessment.weather,
                    "risk": _risk_json(assessment.risk),
                    "hourly": {
                        # Index of the ETA in the departure-relative window; the
                        # client clamps values > SLIDER_HOURS.
                        "index": max(0, eta_idx - departure_idx) if eta_idx >= 0 else None,
                        "wind_mph": forecast["wind_mph"][window],
                        "rain_in_hr": forecast["rain_in_hr"][window],
                        "snow_in_hr": forecast["snow_in_hr"][window],
                        "risk_scores": risk_scores,
                    },
                }
            )

        routes.append(
            {
                "route_id": f"route_{route_no}",
                "summary": {
                    "distance_miles": round(stats.distance_miles, 1),
                    "duration_hours": round(stats.duration_hours, 1),
                    "eta": _iso(stats.eta_epoch),
                    "severe_miles": stats.severe_miles,
                    "high_miles": stats.high_miles,
                    "no_travel_miles": stats.no_travel_miles,
                    "per_level_miles": stats.per_level_miles,
                    "avg_risk_score": stats.avg_risk_score,
                    "avg_risk_label": stats.avg_risk_label,
                },
                "geometry": features[route_no - 1]["geometry"]["coordinates"],
                "checkpoints": checkpoints_json,
            }
        )

    best_index, reason = recommend(stats_list)
    routes[best_index]["is_recommended"] = True
    for i, route in enumerate(routes):
        route.setdefault("is_recommended", False)

    hours_window = []
    if route_checkpoints and forecasts:
        first = forecasts[0]
        departure_idx = max(0, _hour_index(first["hours"], departure_epoch))
        hours_window = first["hours"][departure_idx : departure_idx + SLIDER_HOURS + 1]

    return {
        "origin": {"name": origin["name"], "lat": origin["lat"], "lng": origin["lng"]},
        "destination": {"name": destination["name"], "lat": destination["lat"], "lng": destination["lng"]},
        "departure_time": _iso(departure_epoch),
        "load_weight_lbs": load_lbs,
        "sample_interval_miles": interval_miles,
        "hours": hours_window,
        "recommended_route_id": routes[best_index]["route_id"],
        "recommendation_reason": reason,
        "routes": routes,
        "warnings": warnings,
    }


def _risk_json(risk) -> dict | None:
    if risk is None:
        return None
    return {
        "overall": risk.overall.label,
        "score": risk.score,
        "wind": risk.wind.label,
        "rain": risk.rain.label,
        "snow": risk.snow.label,
        "load_rule_triggered": risk.load_rule_triggered,
    }
