"""Admin panel = the System Administrator's tools (verify licences, manage data)."""
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import Clinic, InsuranceProvider, LicenseVerification, Specialization, Therapist


@admin.register(LicenseVerification)
class LicenseVerificationAdmin(admin.ModelAdmin):
    list_display = ["therapist", "license_number", "status", "submitted_at", "reviewed_at", "document_link"]
    list_filter = ["status"]
    search_fields = ["therapist__full_name", "license_number", "therapist__user__email"]
    readonly_fields = ["therapist", "document_link", "submitted_at", "reviewed_at", "reviewed_by"]
    fields = ["therapist", "license_number", "document_link", "status", "reviewer_note",
              "submitted_at", "reviewed_at", "reviewed_by"]
    actions = ["approve", "reject"]

    @admin.display(description="Document")
    def document_link(self, obj):
        if not obj.document:
            return "—"
        return format_html('<a href="{}" target="_blank">View licence</a>',
                           reverse("license-document", args=[obj.pk]))

    def _review(self, request, queryset, status):
        n = queryset.update(status=status, reviewed_at=timezone.now(), reviewed_by=request.user)
        self.message_user(request, f"{n} licence(s) marked {status.lower()}.")

    @admin.action(description="Approve selected licences")
    def approve(self, request, queryset):
        self._review(request, queryset, LicenseVerification.Status.APPROVED)

    @admin.action(description="Reject selected licences")
    def reject(self, request, queryset):
        self._review(request, queryset, LicenseVerification.Status.REJECTED)

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data:
            obj.reviewed_at = timezone.now()
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)


class LicenseInline(admin.StackedInline):
    model = LicenseVerification
    extra = 0
    fields = ["license_number", "status", "reviewed_at"]
    readonly_fields = ["reviewed_at"]


@admin.register(Therapist)
class TherapistAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "phone", "verification", "offers_in_person", "offers_virtual"]
    list_filter = ["license__status", "specializations", "offers_virtual"]
    search_fields = ["full_name", "user__email", "phone"]
    filter_horizontal = ["specializations", "clinics"]
    inlines = [LicenseInline]

    @admin.display(description="Licence")
    def verification(self, obj):
        lic = getattr(obj, "license", None)
        return lic.get_status_display() if lic else "Not submitted"


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "latitude", "longitude", "operating_hours"]
    search_fields = ["name", "address"]
    filter_horizontal = ["insurance_providers"]


admin.site.register(Specialization)
admin.site.register(InsuranceProvider)
