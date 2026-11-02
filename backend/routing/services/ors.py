"""OpenRouteService client: directions (with alternatives) and geocoding.

Geometry/parsing notes:
- Directions uses the GeoJSON endpoint; each feature carries the polyline
  (`geometry.coordinates`, [lng, lat]), `properties.segments` (steps with
  `way_points` and durations) and `properties.summary` (distance/duration).
- `alternative_routes.target_count` is a maximum — short rural pairs may
  return only 1–2 features. Callers must handle any count >= 1.
- `instructions` stays enabled and `geometry_simplify` false so that
  `way_points` indices align with the polyline (checkpoint interpolation
  depends on it).
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger("routing")

DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
TIMEOUT_S = 10

DEFAULT_PROFILE = "driving-hgv"  # heavy-goods routing; trucks, not cars
MAX_ALTERNATIVES = 3


class UpstreamError(Exception):
    """An external API call failed (network, 5xx, malformed body)."""


class RateLimitError(UpstreamError):
    """The upstream API rate limit was hit (HTTP 429)."""


def _headers() -> dict:
    return {"Authorization": settings.ORS_API_KEY, "Content-Type": "application/json"}


def get_directions(origin_lnglat, destination_lnglat, profile: str = DEFAULT_PROFILE) -> list:
    """Fetch up to 3 alternative routes; returns the GeoJSON feature list."""
    body = {
        "coordinates": [list(origin_lnglat), list(destination_lnglat)],
        "alternative_routes": {
            "target_count": MAX_ALTERNATIVES,
            "share_factor": 0.6,
            "weight_factor": 1.6,
        },
        "instructions": True,
        "geometry_simplify": False,
        "elevation": False,
    }
    url = DIRECTIONS_URL.format(profile=profile)

    try:
        response = requests.post(url, json=body, headers=_headers(), timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        logger.warning("ORS directions request failed: %s", exc)
        raise UpstreamError("Routing service is unreachable.") from exc

    if response.status_code == 429:
        logger.warning("ORS directions rate-limited (429).")
        raise RateLimitError("Routing service rate limit hit — try again shortly.")
    if response.status_code >= 400:
        logger.warning("ORS directions HTTP %s: %s", response.status_code, response.text[:300])
        raise UpstreamError("Routing service rejected the request.")

    try:
        features = response.json()["features"]
    except (ValueError, KeyError) as exc:
        logger.warning("ORS directions returned malformed body.")
        raise UpstreamError("Routing service returned an unusable response.") from exc

    if not features:
        raise UpstreamError("No route found between the given points.")
    return features


def geocode(text: str, size: int = 5) -> list:
    """Forward geocoding; returns [{name, lat, lng}, ...] best-first."""
    try:
        response = requests.get(
            GEOCODE_URL,
            params={"api_key": settings.ORS_API_KEY, "text": text, "size": size},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        logger.warning("ORS geocode request failed: %s", exc)
        raise UpstreamError("Geocoding service is unreachable.") from exc

    if response.status_code == 429:
        logger.warning("ORS geocode rate-limited (429).")
        raise RateLimitError("Geocoding rate limit hit — try again shortly.")
    if response.status_code >= 400:
        logger.warning("ORS geocode HTTP %s: %s", response.status_code, response.text[:300])
        raise UpstreamError("Geocoding service rejected the request.")

    try:
        features = response.json()["features"]
    except (ValueError, KeyError) as exc:
        logger.warning("ORS geocode returned malformed body.")
        raise UpstreamError("Geocoding service returned an unusable response.") from exc

    results = []
    for feature in features:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates") or [None, None]
        label = feature.get("properties", {}).get("label")
        if coords[0] is None or coords[1] is None or not label:
            continue
        results.append({"name": label, "lng": coords[0], "lat": coords[1]})
    return results
