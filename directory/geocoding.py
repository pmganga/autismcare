"""Address -> coordinates via the external mapping provider (SRS 3.3).

Uses OpenStreetMap Nominatim by default. Calls time out after 5 seconds
(SRS 3.4); on any failure we return None and the caller falls back to
coordinates entered by hand.
"""
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def geocode(address):
    """Return (lat, lng) for an address, or None if it can't be found."""
    if not address:
        return None
    try:
        r = requests.get(
            settings.GEOCODER_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": settings.GEOCODER_USER_AGENT},
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Geocoding failed for %r: %s", address, e)
        return None
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])
