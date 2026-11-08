"""Load demo data for development and testing.

    python manage.py seed                # filter options + ~24 demo therapists
    python manage.py seed --bulk 10000   # also 10,000 clinics for the NFR 1 load test
    python manage.py seed --reset        # delete all demo data first

All demo accounts use the email domain @demo.autismcare.test and fake names.
"""
import random
from math import cos, radians

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import Clinic, InsuranceProvider, LicenseVerification, Specialization, Therapist

DEMO_DOMAIN = "demo.autismcare.test"
DEMO_PASSWORD = "DemoTherapist2026!"

SPECIALIZATIONS = [
    "ABA therapy",
    "Speech and language therapy",
    "Occupational therapy",
    "Sensory integration therapy",
    "Developmental paediatrics",
    "Child psychology",
    "Diagnostic assessment",
    "Special education support",
]

INSURANCE = ["SHA", "Jubilee Health", "AAR", "Britam", "CIC", "Madison", "RSSB"]

# (name, lat, lng): urban and peri-urban towns, per the project's focus.
TOWNS = [
    ("Nairobi", -1.2864, 36.8172),
    ("Kiambu", -1.1714, 36.8356),
    ("Thika", -1.0388, 37.0834),
    ("Machakos", -1.5177, 37.2634),
    ("Kitengela", -1.4744, 36.9600),
    ("Ngong", -1.3624, 36.6560),
    ("Nakuru", -0.3031, 36.0800),
    ("Nyeri", -0.4201, 36.9476),
    ("Kisumu", -0.0917, 34.7680),
    ("Eldoret", 0.5143, 35.2698),
    ("Kigali", -1.9441, 30.0619),
]

FIRST = ["Amani", "Wanjiru", "Otieno", "Akinyi", "Kamau", "Njeri", "Mutua", "Achieng", "Kiprop",
         "Wambui", "Mugisha", "Uwase", "Baraka", "Nyambura", "Ochieng", "Chebet"]
LAST = ["Demo", "Sample", "Example", "Test"]  # obviously fake surnames
PAYMENTS = ["M-Pesa, cash", "M-Pesa, card", "Cash, card, bank transfer", "M-Pesa", "Card"]
HOURS = ["Mon–Fri 08:00–17:00", "Mon–Sat 09:00–16:00", "Tue–Sat 08:30–15:30"]


def jitter(rng, lat, lng, max_km):
    """A random point up to max_km from (lat, lng)."""
    d_lat = rng.uniform(-max_km, max_km) / 111.0
    d_lng = rng.uniform(-max_km, max_km) / (111.0 * cos(radians(lat)))
    return round(lat + d_lat, 6), round(lng + d_lng, 6)


class Command(BaseCommand):
    help = "Load demo specializations, insurers, therapists and clinics."

    def add_arguments(self, parser):
        parser.add_argument("--bulk", type=int, default=0, help="Extra clinics for load testing (e.g. 10000).")
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")

    def handle(self, *args, bulk, reset, **opts):
        rng = random.Random(42)
        User = get_user_model()

        if reset:
            self._reset(User)

        specs = [Specialization.objects.get_or_create(name=n)[0] for n in SPECIALIZATIONS]
        insurers = [InsuranceProvider.objects.get_or_create(name=n)[0] for n in INSURANCE]
        self.stdout.write(f"Filter options: {len(specs)} specializations, {len(insurers)} insurers.")

        if User.objects.filter(email__endswith="@" + DEMO_DOMAIN).exists() and not reset:
            self.stdout.write(self.style.WARNING("Demo therapists already exist. Use --reset to recreate them."))
        else:
            self._demo_therapists(User, rng, specs, insurers)

        if bulk:
            self._bulk(User, rng, bulk, specs, insurers)

    def _reset(self, User):
        demo = Therapist.objects.filter(user__email__endswith="@" + DEMO_DOMAIN)
        Clinic.objects.filter(therapists__in=demo).delete()
        Clinic.objects.filter(name__startswith="[bulk]").delete()
        n, _ = User.objects.filter(email__endswith="@" + DEMO_DOMAIN).delete()
        self.stdout.write(f"Removed demo data ({n} rows).")

    @transaction.atomic
    def _demo_therapists(self, User, rng, specs, insurers):
        statuses = {4: LicenseVerification.Status.PENDING, 5: LicenseVerification.Status.REJECTED}
        for i in range(24):
            town, lat, lng = TOWNS[i % len(TOWNS)]
            name = f"{FIRST[i % len(FIRST)]} {LAST[i % len(LAST)]}"
            user = User.objects.create_user(email=f"therapist{i + 1:02d}@{DEMO_DOMAIN}", password=DEMO_PASSWORD)
            t = Therapist.objects.create(
                user=user,
                full_name=name,
                phone=f"+254 700 000 {i + 1:03d}",
                bio=f"Demo profile. Works with autistic children and their families around {town}.",
                offers_in_person=i % 4 != 3,
                offers_virtual=i % 3 == 0 or i % 4 == 3,
                payment_methods=PAYMENTS[i % len(PAYMENTS)],
            )
            t.specializations.set(rng.sample(specs, k=rng.randint(1, 3)))
            for c in range(1 + (i % 2)):
                clat, clng = jitter(rng, lat, lng, 15)
                clinic = Clinic.objects.create(
                    name=f"{town} Child Development Centre {c + 1} (demo)",
                    address=f"{town}, Kenya" if town != "Kigali" else "Kigali, Rwanda",
                    latitude=clat,
                    longitude=clng,
                    operating_hours=HOURS[(i + c) % len(HOURS)],
                )
                clinic.insurance_providers.set(rng.sample(insurers, k=rng.randint(1, 3)))
                t.clinics.add(clinic)
            lic = LicenseVerification(
                therapist=t,
                license_number=f"DEMO-{1000 + i}",
                status=statuses.get(i % 6, LicenseVerification.Status.APPROVED),
            )
            lic.document.save("demo-license.pdf", ContentFile(b"%PDF-1.4\n% demo licence\n"), save=False)
            lic.save()
        self.stdout.write(self.style.SUCCESS(
            f"Created 24 demo therapists (16 approved, 4 pending, 4 rejected). "
            f"Login: therapist01@{DEMO_DOMAIN} / {DEMO_PASSWORD}"
        ))

    @transaction.atomic
    def _bulk(self, User, rng, n_clinics, specs, insurers):
        per_therapist = 5
        n_therapists = max(1, n_clinics // per_therapist)
        self.stdout.write(f"Bulk: creating {n_clinics} clinics and {n_therapists} therapists…")
        start = User.objects.filter(email__startswith="bulk", email__endswith="@" + DEMO_DOMAIN).count()
        pw = make_password(DEMO_PASSWORD)

        users = User.objects.bulk_create(
            [User(email=f"bulk{start + k:05d}@{DEMO_DOMAIN}", password=pw) for k in range(n_therapists)]
        )
        therapists = Therapist.objects.bulk_create(
            [Therapist(user=u, full_name=f"Bulk Therapist {start + k:05d}", phone="+254 700 999 999",
                       offers_in_person=True, offers_virtual=k % 2 == 0, payment_methods="M-Pesa")
             for k, u in enumerate(users)]
        )
        clinics = []
        for k in range(n_clinics):
            town, lat, lng = TOWNS[k % len(TOWNS)]
            clat, clng = jitter(rng, lat, lng, 60)
            clinics.append(Clinic(name=f"[bulk] {town} clinic {start * per_therapist + k:05d}",
                                  address=town, latitude=clat, longitude=clng,
                                  operating_hours=HOURS[k % len(HOURS)]))
        clinics = Clinic.objects.bulk_create(clinics, batch_size=2000)

        TC = Therapist.clinics.through
        TC.objects.bulk_create(
            [TC(therapist_id=t.pk, clinic_id=clinics[i * per_therapist + j].pk)
             for i, t in enumerate(therapists) for j in range(per_therapist)
             if i * per_therapist + j < len(clinics)],
            batch_size=5000,
        )
        TS = Therapist.specializations.through
        TS.objects.bulk_create(
            [TS(therapist_id=t.pk, specialization_id=specs[i % len(specs)].pk) for i, t in enumerate(therapists)],
            batch_size=5000,
        )
        CI = Clinic.insurance_providers.through
        CI.objects.bulk_create(
            [CI(clinic_id=c.pk, insuranceprovider_id=insurers[i % len(insurers)].pk) for i, c in enumerate(clinics)],
            batch_size=5000,
        )
        LicenseVerification.objects.bulk_create(
            [LicenseVerification(therapist=t, license_number=f"BULK-{t.pk}", document="licenses/bulk.pdf",
                                 status=LicenseVerification.Status.APPROVED) for t in therapists],
            batch_size=5000,
        )
        self.stdout.write(self.style.SUCCESS(f"Bulk data loaded: {len(clinics)} clinics."))
