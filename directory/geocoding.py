"""Turns an address into coordinates with OpenStreetMap Nominatim (SRS 3.3).

Calls stop after 5 seconds (SRS 3.4). If it fails, the therapist types the coordinates instead.
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
