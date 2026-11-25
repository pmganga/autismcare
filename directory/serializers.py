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


class NearbyClinicSerializer(serializers.ModelSerializer):
    distance_km = serializers.SerializerMethodField()
    insurance_providers = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)

    class Meta:
        model = Clinic
        fields = ["id", "name", "address", "latitude", "longitude", "operating_hours",
                  "insurance_providers", "distance_km"]

    def get_distance_km(self, obj):
        return round(obj.distance_km, 1)


class SearchResultSerializer(serializers.ModelSerializer):
    """Public view of a verified therapist in search results."""

    distance_km = serializers.SerializerMethodField()
    specializations = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    consultation_modes = serializers.ListField(read_only=True)
    clinics = NearbyClinicSerializer(source="nearby_clinics", many=True, read_only=True)

    class Meta:
        model = Therapist
        fields = ["id", "full_name", "phone", "specializations", "consultation_modes",
                  "payment_methods", "distance_km", "clinics"]

    def get_distance_km(self, obj):
        return round(obj.distance_km, 1)


class PublicTherapistSerializer(serializers.ModelSerializer):
    specializations = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    consultation_modes = serializers.ListField(read_only=True)
    clinics = ClinicSerializer(many=True, read_only=True)

    class Meta:
        model = Therapist
        fields = ["id", "full_name", "phone", "bio", "specializations", "consultation_modes",
                  "payment_methods", "clinics"]
