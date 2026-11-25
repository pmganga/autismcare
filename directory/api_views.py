"""Directory REST endpoints (FR 3.1, 3.2, 3.3)."""
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .geocoding import geocode
from .models import InsuranceProvider, LicenseVerification, Specialization, Therapist
from .permissions import IsTherapist
from .search import SearchError, parse_params, search_therapists
from .serializers import (
    ClinicSerializer,
    LicenseSerializer,
    PublicTherapistSerializer,
    TherapistProfileSerializer,
    search_result,
)
from .services import submit_license


# --- Therapist's own data ---------------------------------------------------
class MyProfileView(generics.RetrieveUpdateAPIView):
    """GET/PUT/PATCH /api/therapists/me/"""

    serializer_class = TherapistProfileSerializer
    permission_classes = [IsTherapist]

    def get_object(self):
        return self.request.user.therapist_profile


class MyClinicsView(generics.ListCreateAPIView):
    """GET/POST /api/clinics/ — the therapist's own clinics."""

    serializer_class = ClinicSerializer
    permission_classes = [IsTherapist]

    def get_queryset(self):
        return self.request.user.therapist_profile.clinics.prefetch_related("insurance_providers")

    def perform_create(self, serializer):
        clinic = serializer.save()
        self.request.user.therapist_profile.clinics.add(clinic)


class MyClinicDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/clinics/<id>/ — only clinics the therapist practises at."""

    serializer_class = ClinicSerializer
    permission_classes = [IsTherapist]

    def get_queryset(self):
        return self.request.user.therapist_profile.clinics.all()

    def perform_destroy(self, clinic):
        # Remove the link; delete the clinic only if nobody else practises there.
        self.request.user.therapist_profile.clinics.remove(clinic)
        if not clinic.therapists.exists():
            clinic.delete()


class MyLicenseView(APIView):
    """GET/POST /api/therapists/me/license/ — upload sets status to PENDING."""

    permission_classes = [IsTherapist]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        lic = getattr(request.user.therapist_profile, "license", None)
        if lic is None:
            return Response({"status": "NOT_SUBMITTED"})
        return Response(LicenseSerializer(lic).data)

    def post(self, request):
        s = LicenseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lic = submit_license(
            request.user.therapist_profile, s.validated_data["license_number"], s.validated_data["document"]
        )
        return Response(LicenseSerializer(lic).data, status=status.HTTP_201_CREATED)


# --- Public search ------------------------------------------------------------
class TherapistSearchView(APIView):
    """GET /api/therapists/search/?lat=&lng=&radius=&specialization=&insurance=&mode="""

    def get(self, request):
        try:
            params = parse_params(request.query_params)
        except SearchError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        results = search_therapists(params)
        return Response(
            {
                "count": len(results),
                "total": results.total,
                "radius_km": params.radius_km,
                "results": [search_result(t) for t in results],
            }
        )


class PublicTherapistView(generics.RetrieveAPIView):
    """GET /api/therapists/<id>/ — verified therapists only."""

    serializer_class = PublicTherapistSerializer

    def get_object(self):
        return get_object_or_404(
            Therapist.objects.prefetch_related("specializations", "clinics__insurance_providers"),
            pk=self.kwargs["pk"],
            license__status=LicenseVerification.Status.APPROVED,
        )


class FilterOptionsView(APIView):
    """GET /api/filter-options/ — values for the search page dropdowns."""

    def get(self, request):
        return Response(
            {
                "specializations": list(Specialization.objects.values_list("name", flat=True)),
                "insurance_providers": list(InsuranceProvider.objects.values_list("name", flat=True)),
                "modes": [{"value": "in_person", "label": "In-person"}, {"value": "virtual", "label": "Virtual"}],
            }
        )


class GeocodeView(APIView):
    """GET /api/geocode/?q=<place> — for typed-in locations on the search page."""

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"detail": "Type a place name."}, status=status.HTTP_400_BAD_REQUEST)
        coords = geocode(q)
        if coords is None:
            return Response(
                {"detail": "We couldn't find that place. Try a nearby town name."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"lat": coords[0], "lng": coords[1]})
