"""Admin "Monitor System Performance" page (use case diagram: System Administrator)."""
import statistics
import time
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from directory.models import Clinic, LicenseVerification, Therapist
from learning.models import Flashcard, LearningSession
from screening.models import RiskResult

from .middleware import RECENT, STARTED

TARGET_MS = 500  # NFR 1


def summarise(timings):
    if not timings:
        return None
    ordered = sorted(timings)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "slowest": ordered[-1],
        "under_target": sum(ms <= TARGET_MS for ms in ordered) * 100 / len(ordered),
    }


def database_ms():
    start = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return (time.perf_counter() - start) * 1000


@staff_member_required
def performance(request):
    recent = list(RECENT)
    since_hour = time.time() - 3600
    last_hour = [r for r in recent if r[0] >= since_hour]
    week_ago = timezone.now() - timedelta(days=7)
    context = {
        "title": "System performance",
        "uptime": timedelta(seconds=int(time.time() - STARTED)),
        "database_ms": database_ms(),
        "all_requests": summarise([r[3] for r in recent]),
        "search": summarise([r[3] for r in recent if r[1].startswith("/api/therapists/search")]),
        "errors": sum(r[2] >= 500 for r in last_hour),
        "requests_last_hour": len(last_hour),
        "slowest": sorted(recent, key=lambda r: r[3], reverse=True)[:5],
        "target_ms": TARGET_MS,
        "therapists": Therapist.objects.count(),
        "licences": dict(LicenseVerification.objects.order_by().values_list("status").annotate(n=Count("id"))),
        "clinics": Clinic.objects.count(),
        "screenings_total": RiskResult.objects.count(),
        "screenings_week": dict(RiskResult.objects.filter(calculated_at__gte=week_ago).order_by()
                                .values_list("tier").annotate(n=Count("id"))),
        "sessions_week": LearningSession.objects.filter(started_at__gte=week_ago).count(),
        "flashcards": dict(Flashcard.objects.filter(is_active=True).order_by().values_list("source").annotate(n=Count("id"))),
    }
    return render(request, "admin/performance.html", context)
