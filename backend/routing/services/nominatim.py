"""Nominatim (OpenStreetMap) fallback geocoder.

Used when the primary OpenRouteService geocoder fails — its free tier has
hard daily quotas, so a 403 "Quota exceeded" must not take autocomplete and
trip planning down with it. The Nominatim usage policy requires identifying
requests with a descriptive User-Agent; light, cached, debounced use (the
client debounces 300 ms, results are cached 24 h) stays well inside it.

Result shape matches ors.geocode: [{name, lat, lng}, ...] best-first.
"""

import logging

import requests
from django.core.cache import cache

from .ors import GEOCODE_CACHE_TTL, RateLimitError, UpstreamError

logger = logging.getLogger("routing")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
TIMEOUT_S = 10
# Identifies the application, per https://operations.osmfoundation.org/policies/nominatim/
USER_AGENT = "weather-aware-truck-routing/1.0"


def _cache_key(text: str, size: int) -> str:
    return f"geocode-nominatim:{text.lower()}:{size}"


def geocode(text: str, size: int = 5) -> list:
    """Forward geocoding; returns [{name, lat, lng}, ...] best-first (cached 24 h)."""
    key = _cache_key(text, size)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": text, "format": "jsonv2", "limit": size},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        logger.warning("Nominatim geocode request failed: %s", exc)
        raise UpstreamError("Geocoding service is unreachable.") from exc

    if response.status_code == 429:
        logger.warning("Nominatim geocode rate-limited (429).")
        raise RateLimitError("Geocoding rate limit hit — try again shortly.")
    if response.status_code >= 400:
        logger.warning("Nominatim geocode HTTP %s: %s", response.status_code, response.text[:300])
        raise UpstreamError("Geocoding service rejected the request.")

    try:
        places = response.json()
    except ValueError:
        places = None
    if not isinstance(places, list):
        logger.warning("Nominatim geocode returned malformed body.")
        raise UpstreamError("Geocoding service returned an unusable response.")

    results = []
    for place in places or []:
        name = place.get("display_name")
        try:
            lat, lng = float(place["lat"]), float(place["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not name:
            continue
        results.append({"name": name, "lng": lng, "lat": lat})

    cache.set(key, results, GEOCODE_CACHE_TTL)
    return results
