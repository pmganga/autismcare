"""Screening web pages.

The browser can view a result only if this browser submitted it. The result's
ID is remembered in the Django session (a cookie), never alongside any personal data.
"""
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .content import AGE_MESSAGE, DISCLAIMER, MAX_AGE_MONTHS, MIN_AGE_MONTHS, TIER_GUIDANCE
from .models import ScreeningSession
from .services import active_questions, submit_screening

SESSION_KEY = "screening_ids"


def _ctx(**extra):
    return {"disclaimer": DISCLAIMER, "min_age": MIN_AGE_MONTHS, "max_age": MAX_AGE_MONTHS, **extra}


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
    if str(pk) not in request.session.get(SESSION_KEY, []):
        raise Http404
    session = get_object_or_404(ScreeningSession.objects.select_related("result"), pk=pk)
    res = session.result
    return render(request, "screening/result.html", _ctx(
        session=session, result=res, guidance=TIER_GUIDANCE[res.tier],
    ))
