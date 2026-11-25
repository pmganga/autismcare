"""Directory module models, following the SRS class diagram (Appendix B.2)."""
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models


class Specialization(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InsuranceProvider(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Clinic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    operating_hours = models.CharField(max_length=200, help_text="e.g. Mon–Fri 08:00–17:00")
    insurance_providers = models.ManyToManyField(InsuranceProvider, blank=True, related_name="clinics")

    class Meta:
        ordering = ["name"]
        # Composite index for the bounding-box pre-filter in radius search (NFR 1).
        indexes = [models.Index(fields=["latitude", "longitude"], name="clinic_lat_lng_idx")]

    def __str__(self):
        return self.name


class Therapist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="therapist_profile"
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    bio = models.TextField(blank=True)
    offers_in_person = models.BooleanField("Offers in-person sessions", default=True)
    offers_virtual = models.BooleanField("Offers virtual sessions", default=False)
    payment_methods = models.CharField(max_length=200, blank=True, help_text="e.g. M-Pesa, cash, card")
    specializations = models.ManyToManyField(Specialization, blank=True, related_name="therapists")
    clinics = models.ManyToManyField(Clinic, blank=True, related_name="therapists")

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def is_verified(self):
        lic = getattr(self, "license", None)
        return lic is not None and lic.status == LicenseVerification.Status.APPROVED

    @property
    def consultation_modes(self):
        modes = []
        if self.offers_in_person:
            modes.append("In-person")
        if self.offers_virtual:
            modes.append("Virtual")
        return modes


def license_upload_path(instance, filename):
    return f"licenses/{instance.therapist_id}/{uuid.uuid4().hex}_{filename}"


class LicenseVerification(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    therapist = models.OneToOneField(Therapist, on_delete=models.CASCADE, related_name="license")
    license_number = models.CharField(max_length=100)
    document = models.FileField(
        upload_to=license_upload_path,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    submitted_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewer_note = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.therapist} – {self.get_status_display()}"
