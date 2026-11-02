"""Open-Meteo batched hourly forecast client.

Open-Meteo is free and keyless, and accepts many locations per request:
`latitude=a,b,c&longitude=x,y,z` returns a JSON **array** in input order
(a single location returns an object — normalized here). This client batches
all checkpoints of all routes into chunks of 100 pairs.

Units are requested natively — `wind_speed_unit=mph` and
`precipitation_unit=inch` (applies to both `rain` and `snowfall`) — so no
unit conversion happens anywhere in this codebase.

`timeformat=unixtime` returns the hourly grid as UTC epoch seconds, which
makes ETA matching pure integer math. Although 72 h are fetched (ETA risk
lookups for long trips), client-facing series are truncated to 49 entries —
the 0–48 h slider window. Null entries are kept as None (model gaps).
"""

import logging

import requests

logger = logging.getLogger("routing")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 10
BATCH_SIZE = 100  # coordinate pairs per request
HOURS_NEEDED = 49  # slider window: hours 0..48 inclusive


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
    """One location's response -> {hours, wind_mph, rain_in_hr, snow_in_hr} (truncated)."""
    hourly = entry["hourly"]

    def _series(key):
        return hourly[key][:HOURS_NEEDED]

    return {
        "hours": _series("time"),
        "wind_mph": _series("wind_speed_10m"),
        "rain_in_hr": _series("rain"),
        "snow_in_hr": _series("snowfall"),
    }


def _fetch_chunk(latitudes, longitudes) -> list:
    try:
        response = requests.get(FORECAST_URL, params=_build_params(latitudes, longitudes), timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        raise UpstreamError("Weather service is unreachable.") from exc

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


def get_hourly_forecasts(points: list) -> list:
    """Hourly series per point, in input order.

    points: [(lat, lng), ...] — returns the same number of entries, each
    {hours, wind_mph, rain_in_hr, snow_in_hr} truncated to HOURS_NEEDED.
    """
    if not points:
        return []

    results = []
    for start in range(0, len(points), BATCH_SIZE):
        chunk = points[start : start + BATCH_SIZE]
        results.extend(_fetch_chunk([p[0] for p in chunk], [p[1] for p in chunk]))
    return results
