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

Long-route alternatives: the public ORS API only allows the
`alternative_routes` algorithm for routes up to ~100 km (error code 2004).
For longer trips we synthesize corridor alternatives instead: the direct
route plus one route via a north-offset via-point and one via a
south-offset via-point. Each is a genuine HGV-profile route from the same
routing engine; duplicates (nearly identical distance) are dropped.
"""

import hashlib
import json
import logging
import math
import time

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("routing")

DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
TIMEOUT_S = 10

DEFAULT_PROFILE = "driving-hgv"  # heavy-goods routing; trucks, not cars
MAX_ALTERNATIVES = 3

TRANSIENT_STATUS = (500, 502, 503, 504)
RETRY_BACKOFF_S = 1
DIRECTIONS_CACHE_TTL = 60 * 60  # also stabilizes ORS alternative randomness
GEOCODE_CACHE_TTL = 24 * 60 * 60

# ORS "Request parameters exceed the server configuration limits" for the
# alternatives algorithm (distance cap on the public API).
_ALTERNATIVES_LIMIT_CODE = 2004

_M_PER_DEG_LAT = 11_0540.0  # ~110,540 m per degree of latitude
_M_PER_DEG_LNG = 111_320.0  # at the equator; scaled by cos(latitude)
_VIA_OFFSET_FRACTION = 0.12  # detour via-point offset as a share of route length


class UpstreamError(Exception):
    """An external API call failed (network, 5xx, malformed body)."""


class RateLimitError(UpstreamError):
    """The upstream API rate limit was hit (HTTP 429)."""


def _headers() -> dict:
    return {"Authorization": settings.ORS_API_KEY, "Content-Type": "application/json"}


def _directions_body(coordinates, alternatives: bool) -> dict:
    body = {
        "coordinates": [list(c) for c in coordinates],
        "instructions": True,
        "geometry_simplify": False,
        "elevation": False,
        # Unlimited snap radius: geocoded city centroids and synthetic via
        # points may sit far from any HGV-routable road; ORS otherwise
        # rejects them when nothing routable is within 350 m.
        "radiuses": [-1] * len(coordinates),
    }
    if alternatives:
        body["alternative_routes"] = {
            "target_count": MAX_ALTERNATIVES,
            "share_factor": 0.6,
            "weight_factor": 1.6,
        }
    return body


def _post(body: dict, url: str) -> list | None:
    """POST to ORS; returns features or None when ORS rejected the request.

    One retry with backoff on transient 5xx / network errors. 429s raise;
    other >=400 responses return None so the caller can decide on a fallback.
    """
    for attempt in (0, 1):
        try:
            response = requests.post(url, json=body, headers=_headers(), timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_S)
                continue
            logger.warning("ORS directions request failed: %s", exc)
            raise UpstreamError("Routing service is unreachable.") from exc

        if response.status_code == 429:
            logger.warning("ORS directions rate-limited (429).")
            raise RateLimitError("Routing service rate limit hit — try again shortly.")
        if response.status_code in TRANSIENT_STATUS and attempt == 0:
            time.sleep(RETRY_BACKOFF_S)
            continue
        break

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code >= 400:
        logger.warning("ORS directions HTTP %s: %s", response.status_code, response.text[:300])
        return None

    features = (payload or {}).get("features")
    if not features:
        return None
    return features


def _is_alternatives_limit_rejection(payload) -> bool:
    error = (payload or {}).get("error") if isinstance(payload, dict) else None
    return bool(error) and error.get("code") == _ALTERNATIVES_LIMIT_CODE


def _via_points(origin_lnglat, destination_lnglat) -> list:
    """Two detour via-points, offset perpendicular to the straight line."""
    lng1, lat1 = origin_lnglat
    lng2, lat2 = destination_lnglat
    mid_lat = math.radians((lat1 + lat2) / 2)

    dx = (lng2 - lng1) * _M_PER_DEG_LNG * math.cos(mid_lat)
    dy = (lat2 - lat1) * _M_PER_DEG_LAT
    length = math.hypot(dx, dy)
    if length == 0:
        return []

    offset_m = length * _VIA_OFFSET_FRACTION
    d_lat = offset_m / _M_PER_DEG_LAT
    d_lng = offset_m / (_M_PER_DEG_LNG * math.cos(mid_lat))

    # Unit perpendicular to the line, then ± offset around mid-route points.
    px, py = -dy / length, dx / length
    sign_lng = 1 if px >= 0 else -1
    sign_lat = 1 if py >= 0 else -1

    via1 = [
        lng1 + (lng2 - lng1) * 0.45 + sign_lng * d_lng,
        lat1 + (lat2 - lat1) * 0.45 + sign_lat * d_lat,
    ]
    via2 = [
        lng1 + (lng2 - lng1) * 0.55 - sign_lng * d_lng,
        lat1 + (lat2 - lat1) * 0.55 - sign_lat * d_lat,
    ]
    return [via1, via2]


def _dedupe_routes(features: list) -> list:
    """Drop routes whose distance is within 1% of an already-kept route."""
    kept = []
    distances = []
    for feature in features:
        distance = feature.get("properties", {}).get("summary", {}).get("distance", 0)
        if any(abs(distance - d) / max(d, 1) < 0.01 for d in distances):
            continue
        kept.append(feature)
        distances.append(distance)
    return kept


def _cache_key(prefix: str, value) -> str:
    digest = hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
    return f"{prefix}:{digest}"


def get_directions(origin_lnglat, destination_lnglat, profile: str = DEFAULT_PROFILE) -> list:
    """Up to 3 routes between two points, as a list of GeoJSON features.

    Cached for 1 h per (origin, destination, profile) — cheaper on ORS's
    40 req/min free quota and stabilizes alternative randomness between
    reloads.

    Strategy: ORS native alternatives when the pair qualifies (<= ~100 km);
    otherwise direct route + two via-point corridor routes.
    """
    key = _cache_key("directions", [origin_lnglat, destination_lnglat, profile])
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = DIRECTIONS_URL.format(profile=profile)
    features = _post(_directions_body([origin_lnglat, destination_lnglat], True), url)
    if features:
        routes = features[:MAX_ALTERNATIVES]
        cache.set(key, routes, DIRECTIONS_CACHE_TTL)
        return routes

    # Retry once without alternatives to distinguish "too long for the
    # alternatives algorithm" from a genuinely unroutable pair.
    features = _post(_directions_body([origin_lnglat, destination_lnglat], False), url)
    if not features:
        raise UpstreamError("No route found between the given points.")

    logger.info("Pair too long for ORS alternatives; building via-point corridor routes.")
    routes = list(features)
    for via in _via_points(origin_lnglat, destination_lnglat):
        via_features = _post(
            _directions_body([origin_lnglat, via, destination_lnglat], False), url
        )
        if via_features:
            routes.extend(via_features)

    routes = _dedupe_routes(routes)[:MAX_ALTERNATIVES]
    if not routes:
        raise UpstreamError("No route found between the given points.")
    cache.set(key, routes, DIRECTIONS_CACHE_TTL)
    return routes


def geocode(text: str, size: int = 5) -> list:
    """Forward geocoding; returns [{name, lat, lng}, ...] best-first (cached 24 h)."""
    key = _cache_key("geocode", [text, size])
    cached = cache.get(key)
    if cached is not None:
        return cached

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

    cache.set(key, results, GEOCODE_CACHE_TTL)
    return results
