"""Radius search and filtering (FR 3.1, FR 3.2, NFR 1).

Two stages, both run inside the database:
1. Bounding box: an indexed range query keeps only clinics inside a square
   around the user, so the expensive maths runs on few rows.
2. Great-circle distance (spherical law of cosines) on the remaining rows,
   keeping clinics inside the circle.

Only therapists whose licence is APPROVED are ever returned.
"""
from collections import defaultdict
from dataclasses import dataclass
from math import cos, radians, sin

from django.conf import settings
from django.db.models import F, FloatField, Value
from django.db.models.functions import ACos, Cos, Least, Radians, Sin

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


def _distance_expr(lat, lng, prefix=""):
    """Distance in km from (lat, lng) to each row's clinic coordinates."""
    lat_f, lng_f = F(prefix + "latitude"), F(prefix + "longitude")
    lat_r, lng_r = radians(lat), radians(lng)
    cos_angle = (
        Value(cos(lat_r)) * Cos(Radians(lat_f)) * Cos(Radians(lng_f) - Value(lng_r))
        + Value(sin(lat_r)) * Sin(Radians(lat_f))
    )
    # Least(...) guards against rounding pushing the value just above 1.
    return Value(EARTH_RADIUS_KM) * ACos(Least(cos_angle, Value(1.0), output_field=FloatField()))


def _bounding_box(p: SearchParams):
    d_lat = p.radius_km / KM_PER_DEGREE_LAT
    d_lng = p.radius_km / (KM_PER_DEGREE_LAT * max(cos(radians(p.lat)), 0.01))
    return (p.lat - d_lat, p.lat + d_lat), (p.lng - d_lng, p.lng + d_lng)


def search_therapists(p: SearchParams, limit=None):
    """Return verified therapists with at least one clinic in range, nearest first.

    Each therapist gets `.distance_km` and `.nearby_clinics` (in-range clinics,
    nearest first, each with its own `.distance_km`).

    Query plan (3 queries + 2 prefetches):
      1. One pass over therapist<->clinic links inside the bounding box, with
         every distance computed once in SQL -> (therapist, clinic, km) rows.
      2. Group in Python: nearest clinic per therapist, keep the top `limit`.
      3. Load only those therapists and their in-range clinics for display.
    """
    limit = limit or settings.SEARCH_MAX_RESULTS
    lat_range, lng_range = _bounding_box(p)

    links = Therapist.clinics.through.objects.filter(
        clinic__latitude__range=lat_range,
        clinic__longitude__range=lng_range,
        therapist__license__status=LicenseVerification.Status.APPROVED,
    )
    if p.insurance:
        links = links.filter(clinic__insurance_providers__name__iexact=p.insurance)
    if p.specialization:
        links = links.filter(therapist__specializations__name__iexact=p.specialization)
    if p.mode == "in_person":
        links = links.filter(therapist__offers_in_person=True)
    elif p.mode == "virtual":
        links = links.filter(therapist__offers_virtual=True)

    rows = (
        links.annotate(distance_km=_distance_expr(p.lat, p.lng, prefix="clinic__"))
        .filter(distance_km__lte=p.radius_km)
        .values_list("therapist_id", "clinic_id", "distance_km")
    )

    nearest = {}                      # therapist_id -> km to nearest in-range clinic
    in_range = defaultdict(dict)      # therapist_id -> {clinic_id: km}
    for t_id, c_id, km in rows:
        in_range[t_id][c_id] = km
        if km < nearest.get(t_id, float("inf")):
            nearest[t_id] = km
    top = sorted(nearest, key=lambda t: (nearest[t], t))[:limit]
    if not top:
        return []

    clinic_ids = {c for t in top for c in in_range[t]}
    clinics = Clinic.objects.filter(pk__in=clinic_ids).prefetch_related("insurance_providers").in_bulk()
    therapists = Therapist.objects.filter(pk__in=top).prefetch_related("specializations")

    results = []
    for t in therapists:
        t.distance_km = nearest[t.pk]
        t.nearby_clinics = []
        for c_id, km in sorted(in_range[t.pk].items(), key=lambda kv: kv[1]):
            clinic = clinics[c_id]
            clinic.distance_km = km
            t.nearby_clinics.append(clinic)
        results.append(t)
    results.sort(key=lambda t: (t.distance_km, t.full_name))
    return results
