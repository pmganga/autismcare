"""Shared logic for the API and the web pages."""
from django.conf import settings
from django.core.exceptions import ValidationError

from .geocoding import geocode
from .models import LicenseVerification


def resolve_coordinates(address, lat=None, lng=None):
    """Use hand-entered coordinates if given, otherwise geocode the address.

    Raises ValidationError if neither works.
    """
    if lat is not None and lng is not None:
        return lat, lng
    coords = geocode(address)
    if coords is None:
        raise ValidationError(
            "We couldn't find that address on the map. Check the spelling, "
            "or enter the latitude and longitude by hand."
        )
    return coords


def validate_license_file(f):
    max_bytes = settings.LICENSE_MAX_UPLOAD_MB * 1024 * 1024
    if f.size > max_bytes:
        raise ValidationError(f"The file is too large. The limit is {settings.LICENSE_MAX_UPLOAD_MB} MB.")


def submit_license(therapist, license_number, document):
    """Create or replace the therapist's licence. Any new upload goes back to PENDING."""
    validate_license_file(document)
    lic, _ = LicenseVerification.objects.update_or_create(
        therapist=therapist,
        defaults={
            "license_number": license_number,
            "document": document,
            "status": LicenseVerification.Status.PENDING,
            "reviewed_at": None,
            "reviewed_by": None,
            "reviewer_note": "",
        },
    )
    return lic
