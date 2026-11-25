"""Directory module tests: FR 3.1, FR 3.2, FR 3.3 and verification."""
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Clinic, InsuranceProvider, LicenseVerification, Specialization, Therapist
from .search import SearchError, SearchParams, parse_params, search_therapists

PW = "CorrectHorse-42!"
NAIROBI = (-1.2864, 36.8172)
THIKA = (-1.0388, 37.0834)    # ~40 km from Nairobi
KISUMU = (-0.0917, 34.7680)   # ~265 km from Nairobi


def make_therapist(email, coords, status="APPROVED", specs=(), insurers=(), in_person=True, virtual=False):
    user = get_user_model().objects.create_user(email=email, password=PW)
    t = Therapist.objects.create(user=user, full_name=email.split("@")[0], phone="0700",
                                 offers_in_person=in_person, offers_virtual=virtual)
    t.specializations.set([Specialization.objects.get_or_create(name=s)[0] for s in specs])
    c = Clinic.objects.create(name=f"{email} clinic", address="x", latitude=coords[0],
                              longitude=coords[1], operating_hours="Mon–Fri")
    c.insurance_providers.set([InsuranceProvider.objects.get_or_create(name=i)[0] for i in insurers])
    t.clinics.add(c)
    if status:
        LicenseVerification.objects.create(therapist=t, license_number="L1", document="licenses/x.pdf",
                                           status=status)
    return t


class ParamValidationTests(TestCase):
    def test_radius_bounds(self):
        base = {"lat": "-1.28", "lng": "36.81"}
        for bad in ("4", "51", "abc"):
            with self.assertRaises(SearchError):
                parse_params({**base, "radius": bad})
        self.assertEqual(parse_params({**base, "radius": "5"}).radius_km, 5)
        self.assertEqual(parse_params({**base, "radius": "50"}).radius_km, 50)

    def test_location_required(self):
        with self.assertRaises(SearchError):
            parse_params({"radius": "10"})

    def test_bad_mode(self):
        with self.assertRaises(SearchError):
            parse_params({"lat": "0", "lng": "0", "radius": "10", "mode": "phone"})


class SearchTests(TestCase):
    def setUp(self):
        self.near = make_therapist("near@x.com", (NAIROBI[0] + 0.01, NAIROBI[1]),
                                   specs=["ABA therapy"], insurers=["SHA"], virtual=True)
        self.thika = make_therapist("thika@x.com", THIKA, specs=["Speech and language therapy"],
                                    insurers=["AAR"])
        self.far = make_therapist("far@x.com", KISUMU)
        self.pending = make_therapist("pending@x.com", NAIROBI, status="PENDING")
        self.rejected = make_therapist("rejected@x.com", NAIROBI, status="REJECTED")
        self.none = make_therapist("nolicense@x.com", NAIROBI, status=None)

    def search(self, **kw):
        return search_therapists(SearchParams(lat=NAIROBI[0], lng=NAIROBI[1], **kw))

    def test_radius_and_ordering(self):
        self.assertEqual([t.pk for t in self.search(radius_km=10)], [self.near.pk])
        r50 = self.search(radius_km=50)
        self.assertEqual([t.pk for t in r50], [self.near.pk, self.thika.pk])  # nearest first
        self.assertAlmostEqual(r50[0].distance_km, 1.1, delta=0.2)
        self.assertAlmostEqual(r50[1].distance_km, 40, delta=3)

    def test_only_verified_therapists(self):
        ids = {t.pk for t in self.search(radius_km=50)}
        for t in (self.pending, self.rejected, self.none):
            self.assertNotIn(t.pk, ids)

    def test_filters(self):
        pks = lambda rs: [t.pk for t in rs]
        self.assertEqual(pks(self.search(radius_km=50, specialization="aba therapy")), [self.near.pk])
        self.assertEqual(pks(self.search(radius_km=50, insurance="AAR")), [self.thika.pk])
        self.assertEqual(pks(self.search(radius_km=50, mode="virtual")), [self.near.pk])
        self.assertEqual(pks(self.search(radius_km=50, mode="in_person")), [self.near.pk, self.thika.pk])
        self.assertEqual(pks(self.search(radius_km=50, insurance="AAR", specialization="ABA therapy")), [])

    def test_nearby_clinics_only_in_range(self):
        other = Clinic.objects.create(name="far branch", address="x", latitude=KISUMU[0],
                                      longitude=KISUMU[1], operating_hours="-")
        self.near.clinics.add(other)
        result = self.search(radius_km=10)[0]
        self.assertEqual([c.name for c in result.nearby_clinics], ["near@x.com clinic"])

    def test_api_endpoint(self):
        r = APIClient().get(reverse("api-search"), {"lat": NAIROBI[0], "lng": NAIROBI[1], "radius": 50})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 2)
        first = r.data["results"][0]
        self.assertEqual(first["full_name"], "near")
        self.assertIn("ABA therapy", first["specializations"])
        self.assertEqual(first["clinics"][0]["insurance_providers"], ["SHA"])

    def test_api_rejects_bad_radius(self):
        r = APIClient().get(reverse("api-search"), {"lat": 0, "lng": 0, "radius": 100})
        self.assertEqual(r.status_code, 400)
        self.assertIn("between 5 and 50", r.data["detail"])

    def test_saved_list_cleared_when_data_changes(self):
        self.assertEqual(len(self.search(radius_km=10)), 1)
        lic = self.near.license
        lic.status = "REJECTED"
        lic.save()
        self.assertEqual(len(self.search(radius_km=10)), 0)
        lic.status = "APPROVED"
        lic.save()
        self.assertEqual(len(self.search(radius_km=10, specialization="Play therapy")), 0)
        self.near.specializations.add(Specialization.objects.create(name="Play therapy"))
        self.assertEqual(len(self.search(radius_km=10, specialization="Play therapy")), 1)

    def test_api_reports_server_time(self):
        r = APIClient().get(reverse("api-search"), {"lat": NAIROBI[0], "lng": NAIROBI[1], "radius": 10})
        self.assertRegex(r["Server-Timing"], r"^app;dur=\d+\.\d$")

    def test_public_profile_hidden_until_verified(self):
        self.assertEqual(self.client.get(reverse("therapist-detail", args=[self.near.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("therapist-detail", args=[self.pending.pk])).status_code, 404)
        self.assertEqual(APIClient().get(reverse("api-therapist", args=[self.pending.pk])).status_code, 404)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProfileManagementTests(TestCase):
    def setUp(self):
        self.t = make_therapist("me@x.com", NAIROBI, status=None)
        self.other = make_therapist("other@x.com", THIKA)
        self.api = APIClient()
        self.api.force_authenticate(self.t.user)
        Specialization.objects.get_or_create(name="Occupational therapy")
        InsuranceProvider.objects.get_or_create(name="Britam")

    def test_requires_login(self):
        self.assertIn(APIClient().get(reverse("api-my-profile")).status_code, (401, 403))

    def test_update_profile(self):
        r = self.api.patch(reverse("api-my-profile"), {
            "phone": "+254 711", "offers_virtual": True, "specializations": ["Occupational therapy"],
            "payment_methods": "M-Pesa",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.t.refresh_from_db()
        self.assertEqual(self.t.phone, "+254 711")
        self.assertEqual(list(self.t.specializations.values_list("name", flat=True)), ["Occupational therapy"])

    def test_must_offer_a_mode(self):
        r = self.api.patch(reverse("api-my-profile"), {"offers_in_person": False, "offers_virtual": False},
                           format="json")
        self.assertEqual(r.status_code, 400)

    @patch("directory.services.geocode", return_value=(-1.0, 37.0))
    def test_add_clinic_geocodes_address(self, mock_geo):
        r = self.api.post(reverse("api-my-clinics"), {
            "name": "New", "address": "Thika, Kenya", "operating_hours": "Mon–Fri",
            "insurance_providers": ["Britam"],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["latitude"], r.data["longitude"]), (-1.0, 37.0))
        mock_geo.assert_called_once_with("Thika, Kenya")
        self.assertTrue(self.t.clinics.filter(name="New").exists())

    @patch("directory.services.geocode", return_value=None)
    def test_add_clinic_geocode_failure_gives_clear_error(self, _):
        r = self.api.post(reverse("api-my-clinics"), {
            "name": "New", "address": "nowhere", "operating_hours": "Mon–Fri",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("latitude and longitude", str(r.data))

    @patch("directory.services.geocode")
    def test_manual_coordinates_skip_geocoding(self, mock_geo):
        r = self.api.post(reverse("api-my-clinics"), {
            "name": "Manual", "address": "a village", "operating_hours": "Mon", "latitude": -1.5, "longitude": 37.2,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        mock_geo.assert_not_called()

    def test_cannot_edit_another_therapists_clinic(self):
        clinic = self.other.clinics.first()
        r = self.api.patch(reverse("api-my-clinic", args=[clinic.pk]), {"name": "hacked"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_license_upload_is_pending_and_reupload_resets(self):
        f = SimpleUploadedFile("lic.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.api.post(reverse("api-my-license"), {"license_number": "KE-123", "document": f},
                          format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "PENDING")
        LicenseVerification.objects.filter(therapist=self.t).update(status="APPROVED")
        f2 = SimpleUploadedFile("lic2.pdf", b"%PDF-1.4 new", content_type="application/pdf")
        self.api.post(reverse("api-my-license"), {"license_number": "KE-124", "document": f2}, format="multipart")
        self.assertEqual(LicenseVerification.objects.get(therapist=self.t).status, "PENDING")

    def test_license_rejects_wrong_file_type(self):
        f = SimpleUploadedFile("lic.exe", b"MZ", content_type="application/octet-stream")
        r = self.api.post(reverse("api-my-license"), {"license_number": "KE-1", "document": f},
                          format="multipart")
        self.assertEqual(r.status_code, 400)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AdminVerificationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(email="admin@x.com", password=PW)
        self.t = make_therapist("p@x.com", NAIROBI, status="PENDING")

    def test_admin_approve_action_makes_therapist_searchable(self):
        self.client.force_login(self.admin)
        lic = self.t.license
        # Search first, so the saved list of verified therapists is out of date after approval
        self.assertEqual(len(search_therapists(SearchParams(lat=NAIROBI[0], lng=NAIROBI[1], radius_km=5))), 0)
        r = self.client.post(reverse("admin:directory_licenseverification_changelist"),
                             {"action": "approve", "_selected_action": [lic.pk]})
        self.assertEqual(r.status_code, 302)
        lic.refresh_from_db()
        self.assertEqual(lic.status, "APPROVED")
        self.assertEqual(lic.reviewed_by, self.admin)
        found = search_therapists(SearchParams(lat=NAIROBI[0], lng=NAIROBI[1], radius_km=5))
        self.assertEqual([t.pk for t in found], [self.t.pk])

    def test_licence_file_kept_in_database(self):
        from .models import StoredFile
        from .services import submit_license
        f = SimpleUploadedFile("lic.pdf", b"%PDF-1.4 licence", content_type="application/pdf")
        lic = submit_license(self.t, "KE-9", f)
        stored = StoredFile.objects.get(name=lic.document.name)
        self.assertEqual(bytes(stored.content), b"%PDF-1.4 licence")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("license-document", args=[lic.pk]))
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 licence")

    def test_performance_page_is_staff_only(self):
        self.client.force_login(self.t.user)
        self.assertEqual(self.client.get(reverse("admin-performance")).status_code, 302)
        self.client.force_login(self.admin)
        self.client.get(reverse("find"))
        r = self.client.get(reverse("admin-performance"))
        self.assertContains(r, "System performance")
        self.assertContains(r, "Database reply time")

    def test_license_document_is_staff_only(self):
        url = reverse("license-document", args=[self.t.license.pk])
        self.client.force_login(self.t.user)
        self.assertEqual(self.client.get(url).status_code, 302)  # redirected to admin login
