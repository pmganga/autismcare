from django import forms
from django.core.exceptions import ValidationError

from .models import Clinic, LicenseVerification, Therapist
from .services import resolve_coordinates, validate_license_file


class TherapistProfileForm(forms.ModelForm):
    class Meta:
        model = Therapist
        fields = ["full_name", "phone", "bio", "specializations", "offers_in_person",
                  "offers_virtual", "payment_methods"]
        widgets = {
            "specializations": forms.CheckboxSelectMultiple,
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        data = super().clean()
        if not (data.get("offers_in_person") or data.get("offers_virtual")):
            raise ValidationError("Choose at least one consultation mode.")
        return data


class ClinicForm(forms.ModelForm):
    latitude = forms.FloatField(
        required=False, min_value=-90, max_value=90,
        help_text="Optional. Leave blank and we will find it from the address.",
    )
    longitude = forms.FloatField(required=False, min_value=-180, max_value=180)

    class Meta:
        model = Clinic
        fields = ["name", "address", "operating_hours", "insurance_providers", "latitude", "longitude"]
        widgets = {"insurance_providers": forms.CheckboxSelectMultiple}

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        address_changed = self.instance.pk is None or "address" in self.changed_data
        typed_coords = data.get("latitude") is not None and data.get("longitude") is not None
        if address_changed or typed_coords:
            try:
                data["latitude"], data["longitude"] = resolve_coordinates(
                    data.get("address"), data.get("latitude"), data.get("longitude")
                )
            except ValidationError as e:
                raise ValidationError(e.messages)
        else:
            data["latitude"], data["longitude"] = self.instance.latitude, self.instance.longitude
        return data


class LicenseForm(forms.ModelForm):
    class Meta:
        model = LicenseVerification
        fields = ["license_number", "document"]
        help_texts = {"document": "PDF, JPG or PNG, up to 5 MB."}

    def clean_document(self):
        f = self.cleaned_data["document"]
        validate_license_file(f)
        return f
