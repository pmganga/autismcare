from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClinicForm, LicenseForm, TherapistProfileForm
from .models import LicenseVerification, Therapist
from .services import submit_license


def home(request):
    return render(request, "directory/home.html")


def find_therapist(request):
    return render(request, "directory/find.html")


def therapist_detail(request, pk):
    therapist = get_object_or_404(
        Therapist.objects.prefetch_related("specializations", "clinics__insurance_providers"),
        pk=pk,
        license__status=LicenseVerification.Status.APPROVED,
    )
    return render(request, "directory/therapist_detail.html", {"therapist": therapist})


def _therapist_or_redirect(request):
    profile = getattr(request.user, "therapist_profile", None)
    if profile is None:
        messages.info(request, "The dashboard is for therapist accounts.")
    return profile


@login_required
def dashboard(request):
    if hasattr(request.user, "teacher_profile"):
        return redirect("teach")
    therapist = _therapist_or_redirect(request)
    if therapist is None:
        return redirect("admin:index" if request.user.is_staff else "home")
    form = TherapistProfileForm(request.POST or None, instance=therapist)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been saved.")
        return redirect("dashboard")
    return render(
        request,
        "directory/dashboard.html",
        {
            "therapist": therapist,
            "form": form,
            "license": getattr(therapist, "license", None),
            "clinics": therapist.clinics.prefetch_related("insurance_providers"),
        },
    )


@login_required
def clinic_edit(request, pk=None):
    therapist = _therapist_or_redirect(request)
    if therapist is None:
        return redirect("home")
    clinic = get_object_or_404(therapist.clinics, pk=pk) if pk else None
    form = ClinicForm(request.POST or None, instance=clinic)
    if request.method == "POST" and form.is_valid():
        clinic = form.save(commit=False)
        clinic.latitude = form.cleaned_data["latitude"]
        clinic.longitude = form.cleaned_data["longitude"]
        clinic.save()
        form.save_m2m()
        therapist.clinics.add(clinic)
        messages.success(request, f"“{clinic.name}” has been saved.")
        return redirect("dashboard")
    return render(request, "directory/clinic_form.html", {"form": form, "clinic": clinic})


@login_required
def clinic_remove(request, pk):
    therapist = _therapist_or_redirect(request)
    if therapist is None or request.method != "POST":
        return redirect("dashboard")
    clinic = get_object_or_404(therapist.clinics, pk=pk)
    therapist.clinics.remove(clinic)
    if not clinic.therapists.exists():
        clinic.delete()
    messages.success(request, "Clinic removed.")
    return redirect("dashboard")


@login_required
def license_upload(request):
    therapist = _therapist_or_redirect(request)
    if therapist is None:
        return redirect("home")
    form = LicenseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        submit_license(therapist, form.cleaned_data["license_number"], form.cleaned_data["document"])
        messages.success(request, "Licence submitted. An administrator will review it.")
        return redirect("dashboard")
    return render(
        request, "directory/license_form.html", {"form": form, "license": getattr(therapist, "license", None)}
    )


@staff_member_required
def license_document(request, pk):
    """Staff-only download of a licence document. These files have no public URL."""
    lic = get_object_or_404(LicenseVerification, pk=pk)
    if not lic.document:
        raise Http404
    return FileResponse(lic.document.open("rb"), as_attachment=False)
