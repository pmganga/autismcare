"""Radius search and filtering (FR 3.1, FR 3.2, NFR 1).

Two stages:
1. Bounding box (database): an indexed range query keeps only clinics inside
   a square around the user and returns just IDs and coordinates.
2. Great-circle distance (Python): computed on those rows, keeping clinics
   inside the circle. Doing the maths in Python rather than SQL is fast on any
   database. On SQLite, Django's SQL trig functions run as slow Python
   callbacks, one call per row.

Only therapists whose licence is APPROVED are ever returned.
"""
from collections import defaultdict
from dataclasses import dataclass
from math import acos, cos, radians, sin

from django.conf import settings

from .models import Clinic, LicenseVerification, Therapist

EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE_LAT = 111.0


class SearchError(ValueError):
    pass


@dataclass
class SearchParams:
    lat: float
    lng: float
    radius_km: float
    specialization: str | None = None
    insurance: str | None = None
    mode: str | None = None  # "in_person" | "virtual"


def parse_params(data):
    """Validate raw query parameters. Raises SearchError with a plain-language message."""
    try:
        lat = float(data.get("lat"))
        lng = float(data.get("lng"))
    except (TypeError, ValueError):
        raise SearchError("A location is required. Share your location or type a place name.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise SearchError("That location is not valid.")

    try:
        radius = float(data.get("radius", 10))
    except (TypeError, ValueError):
        raise SearchError("The search radius must be a number.")
    lo, hi = settings.SEARCH_MIN_RADIUS_KM, settings.SEARCH_MAX_RADIUS_KM
    if not lo <= radius <= hi:
        raise SearchError(f"The search radius must be between {lo} and {hi} km.")

    mode = data.get("mode") or None
    if mode not in (None, "in_person", "virtual"):
        raise SearchError("Consultation mode must be 'in_person' or 'virtual'.")

    return SearchParams(
        lat=lat,
        lng=lng,
        radius_km=radius,
        specialization=data.get("specialization") or None,
        insurance=data.get("insurance") or None,
        mode=mode,
    )


def distance_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km (spherical law of cosines)."""
    lat1, lng1, lat2, lng2 = radians(lat1), radians(lng1), radians(lat2), radians(lng2)
    c = sin(lat1) * sin(lat2) + cos(lat1) * cos(lat2) * cos(lng2 - lng1)
    return EARTH_RADIUS_KM * acos(min(1.0, max(-1.0, c)))  # clamp guards against rounding


def _bounding_box(p: SearchParams):
    d_lat = p.radius_km / KM_PER_DEGREE_LAT
    d_lng = p.radius_km / (KM_PER_DEGREE_LAT * max(cos(radians(p.lat)), 0.01))
    return (p.lat - d_lat, p.lat + d_lat), (p.lng - d_lng, p.lng + d_lng)


class SearchResults(list):
    """A list of therapists (nearest first) plus `.total`, the number that matched."""

    total = 0


def search_therapists(p: SearchParams, limit=None):
    """Return verified therapists with at least one clinic in range, nearest first.

    Each therapist gets `.distance_km` and `.nearby_clinics` (up to
    SEARCH_MAX_CLINICS_PER_RESULT in-range clinics, nearest first, each with
    `.distance_km`). The result list has `.total`, the number of matches before `limit`.

    Query plan (NFR 1):
      1. IDs of verified therapists matching the filters.
      2. Therapist-clinic links inside the bounding box via the (latitude,
         longitude) index, with coordinates. In Python: keep eligible
         therapists, compute each clinic's distance once, drop clinics outside
         the circle, nearest clinic per therapist, keep the top `limit`.
      3. Load only those therapists and their few nearest clinics for display.
    """
    limit = limit or settings.SEARCH_MAX_RESULTS
    per_result = settings.SEARCH_MAX_CLINICS_PER_RESULT
    lat_range, lng_range = _bounding_box(p)

    # 1. Verified therapists matching the filters (IDs only).
    # Kept separate from step 2 and joined in Python: combined in one SQL
    # query, SQLite chose a plan that checked every therapist against every clinic.
    eligible = Therapist.objects.filter(license__status=LicenseVerification.Status.APPROVED)
    if p.specialization:
        eligible = eligible.filter(specializations__name__iexact=p.specialization)
    if p.mode == "in_person":
        eligible = eligible.filter(offers_in_person=True)
    elif p.mode == "virtual":
        eligible = eligible.filter(offers_virtual=True)
    eligible_ids = set(eligible.values_list("id", flat=True))

    results = SearchResults()
    if not eligible_ids:
        return results

    # 2. Therapist-clinic links inside the bounding box (lat/lng index), with
    # coordinates; distance computed once per clinic in Python.
    links = Therapist.clinics.through.objects.filter(
        clinic__latitude__range=lat_range, clinic__longitude__range=lng_range
    )
    if p.insurance:
        links = links.filter(clinic__insurance_providers__name__iexact=p.insurance)

    clinic_km = {}
    in_range = defaultdict(list)      # therapist_id -> [(km, clinic_id)]
    for t_id, c_id, lat, lng in links.values_list(
        "therapist_id", "clinic_id", "clinic__latitude", "clinic__longitude"
    ):
        if t_id not in eligible_ids:
            continue
        km = clinic_km.get(c_id)
        if km is None:
            km = clinic_km[c_id] = distance_km(p.lat, p.lng, lat, lng)
        if km <= p.radius_km:
            in_range[t_id].append((km, c_id))
    nearest = {t: min(pairs)[0] for t, pairs in in_range.items()}
    top = sorted(nearest, key=lambda t: (nearest[t], t))[:limit]
    results.total = len(nearest)
    if not top:
        return results

    # 3. Display data for the top results only
    shown = {t: sorted(in_range[t])[:per_result] for t in top}
    clinics = (
        Clinic.objects.filter(pk__in={c for pairs in shown.values() for _, c in pairs})
        .prefetch_related("insurance_providers")
        .in_bulk()
    )
    for t in Therapist.objects.filter(pk__in=top).prefetch_related("specializations"):
        t.distance_km = nearest[t.pk]
        t.nearby_clinics = []
        for km, c_id in shown[t.pk]:
            clinic = clinics[c_id]
            clinic.distance_km = km
            t.nearby_clinics.append(clinic)
        results.append(t)
    results.sort(key=lambda t: (t.distance_km, t.full_name))
    return results
