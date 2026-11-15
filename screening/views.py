"""Screening web pages.

The browser can view a result only if this browser submitted it. The result's
ID is remembered in the Django session (a cookie), never alongside any personal data.
"""
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .content import AGE_MESSAGE, DISCLAIMER, MAX_AGE_MONTHS, MIN_AGE_MONTHS, TIER_GUIDANCE
from .models import RiskTier, ScreeningSession
from .reminder import build_ics
from .report import build_pdf, report_filename
from .rescreen import rescreen_advice
from .services import active_questions, submit_screening

SESSION_KEY = "screening_ids"


def _ctx(**extra):
    return {"disclaimer": DISCLAIMER, "min_age": MIN_AGE_MONTHS, "max_age": MAX_AGE_MONTHS, **extra}


def _own_session(request, pk):
    """The screening, but only if this browser submitted it."""
    if str(pk) not in request.session.get(SESSION_KEY, []):
        raise Http404
    return get_object_or_404(ScreeningSession.objects.select_related("result"), pk=pk)


def _advice(session):
    return rescreen_advice(
        session.child_age_months, session.result.tier, timezone.localtime(session.result.calculated_at).date()
    )


def intro(request):
    return render(request, "screening/intro.html", _ctx())


def questionnaire(request):
    questions = active_questions()
    errors, answers, age = {}, {}, request.POST.get("child_age_months", "")

    if request.method == "POST":
        for q in questions:
            raw = request.POST.get(f"q{q.id}")
            if raw in ("yes", "no"):
                answers[q.id] = raw == "yes"
        try:
            session, result, _token = submit_screening(age, answers)
        except ValidationError as e:
            errors = e.message_dict
        else:
            ids = request.session.get(SESSION_KEY, [])
            request.session[SESSION_KEY] = (ids + [str(session.id)])[-20:]
            return redirect("screening-result", pk=session.id)

    return render(request, "screening/questionnaire.html", _ctx(
        questions=[(q, answers.get(q.id)) for q in questions],
        age=age,
        errors=errors,
        age_out_of_range=AGE_MESSAGE in errors.get("child_age_months", []),
    ))


def result(request, pk):
    session = _own_session(request, pk)
    res = session.result
    return render(request, "screening/result.html", _ctx(
        session=session,
        result=res,
        guidance=TIER_GUIDANCE[res.tier],
        rescreen=_advice(session),
        show_referral=res.tier == RiskTier.HIGH,  # sequence diagram: alt [tier == HIGH]
    ))


def report_pdf(request, pk):
    """FR 2.2: download the PDF guidance report."""
    session = _own_session(request, pk)
    pdf, _ = build_pdf(session, directory_url=request.build_absolute_uri(reverse("find")))
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{report_filename(session)}"'
    return response


def reminder_ics(request, pk):
    """Calendar reminder for the rescreen date."""
    session = _own_session(request, pk)
    advice = _advice(session)
    if advice.due is None:
        raise Http404
    ics = build_ics(advice.due, advice.text, request.build_absolute_uri(reverse("screening")))
    response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="autismcare-rescreen-reminder.ics"'
    return response
