"""Radius search and filtering (FR 3.1, FR 3.2, NFR 1).

Two stages, both run inside the database:
1. Bounding box: an indexed range query keeps only clinics inside a square
   around the user, so the expensive maths runs on few rows.
2. Great-circle distance (spherical law of cosines) on the remaining rows,
   keeping clinics inside the circle.

Only therapists whose licence is APPROVED are ever returned.
"""
from dataclasses import dataclass
from math import cos, radians, sin

from django.conf import settings
from django.db.models import F, FloatField, OuterRef, Prefetch, Q, Subquery, Value
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


def _distance_expr(lat, lng):
    """Distance in km from (lat, lng) to each row's (latitude, longitude)."""
    lat_r, lng_r = radians(lat), radians(lng)
    cos_angle = (
        Value(cos(lat_r)) * Cos(Radians(F("latitude"))) * Cos(Radians(F("longitude")) - Value(lng_r))
        + Value(sin(lat_r)) * Sin(Radians(F("latitude")))
    )
    # Least(...) guards against rounding pushing the value just above 1.
    return Value(EARTH_RADIUS_KM) * ACos(Least(cos_angle, Value(1.0), output_field=FloatField()))


def clinics_within(p: SearchParams):
    d_lat = p.radius_km / KM_PER_DEGREE_LAT
    d_lng = p.radius_km / (KM_PER_DEGREE_LAT * max(cos(radians(p.lat)), 0.01))
    qs = (
        Clinic.objects.filter(
            latitude__range=(p.lat - d_lat, p.lat + d_lat),
            longitude__range=(p.lng - d_lng, p.lng + d_lng),
        )
        .annotate(distance_km=_distance_expr(p.lat, p.lng))
        .filter(distance_km__lte=p.radius_km)
    )
    if p.insurance:
        qs = qs.filter(insurance_providers__name__iexact=p.insurance)
    return qs


def search_therapists(p: SearchParams, limit=None):
    """Return verified therapists with at least one clinic in range, nearest first.

    Each therapist gets `.distance_km` and `.nearby_clinics` (in-range clinics, nearest first).
    """
    limit = limit or settings.SEARCH_MAX_RESULTS
    in_range = clinics_within(p)

    filters = Q(license__status=LicenseVerification.Status.APPROVED) & Q(
        clinics__in=in_range.values("id")
    )
    if p.specialization:
        filters &= Q(specializations__name__iexact=p.specialization)
    if p.mode == "in_person":
        filters &= Q(offers_in_person=True)
    elif p.mode == "virtual":
        filters &= Q(offers_virtual=True)

    nearest = (
        in_range.filter(therapists=OuterRef("pk")).order_by("distance_km").values("distance_km")[:1]
    )
    therapists = (
        Therapist.objects.filter(filters)
        .distinct()
        .annotate(distance_km=Subquery(nearest, output_field=FloatField()))
        .order_by("distance_km", "full_name")
        .select_related("license")
        .prefetch_related(
            "specializations",
            Prefetch(
                "clinics",
                queryset=in_range.order_by("distance_km").prefetch_related("insurance_providers"),
                to_attr="nearby_clinics",
            ),
        )[:limit]
    )
    return list(therapists)
