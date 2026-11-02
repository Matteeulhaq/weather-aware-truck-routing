"""Open-Meteo batched hourly forecast client.

Open-Meteo is free and keyless, and accepts many locations per request:
`latitude=a,b,c&longitude=x,y,z` returns a JSON **array** in input order
(a single location returns an object — normalized here). This client batches
all checkpoints of all routes into chunks of 100 pairs.

Units are requested natively — `wind_speed_unit=mph` and
`precipitation_unit=inch` (applies to both `rain` and `snowfall`) — so no
unit conversion happens anywhere in this codebase.

`timeformat=unixtime` returns the hourly grid as UTC epoch seconds, which
makes ETA matching pure integer math. The full ~72 h grid is returned —
ETA risk lookups need hours well past the 0–48 h slider window; the planner
slices the client-facing 49 h departure-relative window itself. Null entries
are kept as None (model gaps).
"""

import hashlib
import json
import logging
import time

import requests
from django.core.cache import cache

logger = logging.getLogger("routing")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 10
BATCH_SIZE = 100  # coordinate pairs per request
TRANSIENT_STATUS = (500, 502, 503, 504)
RETRY_BACKOFF_S = 1
WEATHER_CACHE_TTL = 15 * 60


class UpstreamError(Exception):
    """The weather API call failed."""


def _build_params(latitudes, longitudes) -> dict:
    return {
        "latitude": ",".join(f"{lat:.6f}" for lat in latitudes),
        "longitude": ",".join(f"{lng:.6f}" for lng in longitudes),
        "hourly": "wind_speed_10m,rain,snowfall",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": 3,
        "timeformat": "unixtime",
    }


def _normalize_series(entry: dict) -> dict:
    """One location's response -> {hours, wind_mph, rain_in_hr, snow_in_hr} (full grid)."""
    hourly = entry["hourly"]
    return {
        "hours": list(hourly["time"]),
        "wind_mph": list(hourly["wind_speed_10m"]),
        "rain_in_hr": list(hourly["rain"]),
        "snow_in_hr": list(hourly["snowfall"]),
    }


def _fetch_chunk(latitudes, longitudes) -> list:
    """One batched request, with one retry on transient failures."""
    for attempt in (0, 1):
        try:
            response = requests.get(FORECAST_URL, params=_build_params(latitudes, longitudes), timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_S)
                continue
            logger.warning("Open-Meteo request failed: %s", exc)
            raise UpstreamError("Weather service is unreachable.") from exc

        if response.status_code in TRANSIENT_STATUS and attempt == 0:
            time.sleep(RETRY_BACKOFF_S)
            continue
        break

    if response.status_code >= 400:
        logger.warning("Open-Meteo HTTP %s: %s", response.status_code, response.text[:300])
        raise UpstreamError("Weather service rejected the request.")

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("Open-Meteo returned malformed body.")
        raise UpstreamError("Weather service returned an unusable response.") from exc

    entries = data if isinstance(data, list) else [data]
    return [_normalize_series(entry) for entry in entries]


def _cache_key(points: list) -> str:
    digest = hashlib.sha1(json.dumps(points).encode()).hexdigest()
    return f"weather:{digest}"


def get_hourly_forecasts(points: list) -> list:
    """Hourly series per point, in input order (cached 15 min per point set).

    points: [(lat, lng), ...] — returns the same number of entries, each
    {hours, wind_mph, rain_in_hr, snow_in_hr} covering the ~72 h grid.
    """
    if not points:
        return []

    key = _cache_key(points)
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = []
    for start in range(0, len(points), BATCH_SIZE):
        chunk = points[start : start + BATCH_SIZE]
        results.extend(_fetch_chunk([p[0] for p in chunk], [p[1] for p in chunk]))

    cache.set(key, results, WEATHER_CACHE_TTL)
    return results
