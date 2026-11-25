from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("find/", views.find_therapist, name="find"),
    path("therapists/<int:pk>/", views.therapist_detail, name="therapist-detail"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/clinics/add/", views.clinic_edit, name="clinic-add"),
    path("dashboard/clinics/<uuid:pk>/edit/", views.clinic_edit, name="clinic-edit"),
    path("dashboard/clinics/<uuid:pk>/remove/", views.clinic_remove, name="clinic-remove"),
    path("dashboard/license/", views.license_upload, name="license-upload"),
    path("staff/licenses/<int:pk>/document/", views.license_document, name="license-document"),
]
