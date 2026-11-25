from django.urls import path

from . import api_views as v

urlpatterns = [
    path("therapists/me/", v.MyProfileView.as_view(), name="api-my-profile"),
    path("therapists/me/license/", v.MyLicenseView.as_view(), name="api-my-license"),
    path("therapists/search/", v.TherapistSearchView.as_view(), name="api-search"),
    path("therapists/<int:pk>/", v.PublicTherapistView.as_view(), name="api-therapist"),
    path("clinics/", v.MyClinicsView.as_view(), name="api-my-clinics"),
    path("clinics/<uuid:pk>/", v.MyClinicDetailView.as_view(), name="api-my-clinic"),
    path("filter-options/", v.FilterOptionsView.as_view(), name="api-filter-options"),
    path("geocode/", v.GeocodeView.as_view(), name="api-geocode"),
]
