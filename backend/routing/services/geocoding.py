"""Geocoding entry point: OpenRouteService first, Nominatim fallback.

The ORS free tier carries hard daily quotas; when it rejects the request
(quota 403, outage, malformed body) or is rate-limited, geocoding degrades
to OpenStreetMap's Nominatim so the autocomplete and trip planning keep
working. Raises ors.UpstreamError (incl. RateLimitError) only when *both*
providers fail.
"""

import logging

from . import nominatim, ors

logger = logging.getLogger("routing")


def geocode(text: str, size: int = 5) -> list:
    try:
        return ors.geocode(text, size)
    except ors.UpstreamError as exc:  # RateLimitError subclasses this
        logger.warning("ORS geocode unavailable (%s); using Nominatim fallback.", exc)
        return nominatim.geocode(text, size)
