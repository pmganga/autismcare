from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Clinic, InsuranceProvider, LicenseVerification, Specialization, Therapist
from .services import resolve_coordinates, validate_license_file


class ClinicSerializer(serializers.ModelSerializer):
    insurance_providers = serializers.SlugRelatedField(
        many=True, slug_field="name", queryset=InsuranceProvider.objects.all(), required=False
    )
    latitude = serializers.FloatField(required=False, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, min_value=-180, max_value=180)

    class Meta:
        model = Clinic
        fields = ["id", "name", "address", "latitude", "longitude", "operating_hours", "insurance_providers"]

    def validate(self, attrs):
        address_changed = "address" in attrs and (
            self.instance is None or attrs["address"] != self.instance.address
        )
        has_coords = "latitude" in attrs and "longitude" in attrs
        if self.instance is None or address_changed or has_coords:
            try:
                attrs["latitude"], attrs["longitude"] = resolve_coordinates(
                    attrs.get("address", getattr(self.instance, "address", "")),
                    attrs.get("latitude"),
                    attrs.get("longitude"),
                )
            except DjangoValidationError as e:
                raise serializers.ValidationError({"address": e.messages})
        return attrs


class TherapistProfileSerializer(serializers.ModelSerializer):
    """The logged-in therapist's own profile (FR 3.3)."""

    email = serializers.EmailField(source="user.email", read_only=True)
    specializations = serializers.SlugRelatedField(
        many=True, slug_field="name", queryset=Specialization.objects.all(), required=False
    )
    clinics = ClinicSerializer(many=True, read_only=True)
    verification_status = serializers.SerializerMethodField()

    class Meta:
        model = Therapist
        fields = [
            "id", "email", "full_name", "phone", "bio", "offers_in_person", "offers_virtual",
            "payment_methods", "specializations", "clinics", "verification_status",
        ]

    def get_verification_status(self, obj):
        lic = getattr(obj, "license", None)
        return lic.status if lic else "NOT_SUBMITTED"

    def validate(self, attrs):
        in_person = attrs.get("offers_in_person", getattr(self.instance, "offers_in_person", True))
        virtual = attrs.get("offers_virtual", getattr(self.instance, "offers_virtual", False))
        if not (in_person or virtual):
            raise serializers.ValidationError("Choose at least one consultation mode.")
        return attrs


class LicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseVerification
        fields = ["license_number", "document", "status", "submitted_at", "reviewed_at", "reviewer_note"]
        read_only_fields = ["status", "submitted_at", "reviewed_at", "reviewer_note"]
        extra_kwargs = {"document": {"write_only": True}}

    def validate_document(self, f):
        try:
            validate_license_file(f)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)
        return f


# Search results are built as plain dictionaries: on the busiest endpoint
# this is several times faster than a DRF serializer (NFR 1).
def search_result(therapist):
    """Public view of a verified therapist in search results."""
    return {
        "id": therapist.id,
        "full_name": therapist.full_name,
        "phone": therapist.phone,
        "specializations": [s.name for s in therapist.specializations.all()],
        "consultation_modes": therapist.consultation_modes,
        "payment_methods": therapist.payment_methods,
        "distance_km": round(therapist.distance_km, 1),
        "clinics": [nearby_clinic(c) for c in therapist.nearby_clinics],
    }


def nearby_clinic(clinic):
    return {
        "id": str(clinic.id),
        "name": clinic.name,
        "address": clinic.address,
        "latitude": clinic.latitude,
        "longitude": clinic.longitude,
        "operating_hours": clinic.operating_hours,
        "insurance_providers": [i.name for i in clinic.insurance_providers.all()],
        "distance_km": round(clinic.distance_km, 1),
    }


class PublicTherapistSerializer(serializers.ModelSerializer):
    specializations = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    consultation_modes = serializers.ListField(read_only=True)
    clinics = ClinicSerializer(many=True, read_only=True)

    class Meta:
        model = Therapist
        fields = ["id", "full_name", "phone", "bio", "specializations", "consultation_modes",
                  "payment_methods", "clinics"]
