"""Submitting a screening. Shared by the API and the web pages."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .content import AGE_MESSAGE, MAX_AGE_MONTHS, MIN_AGE_MONTHS
from .models import Answer, Question, RiskResult, ScreeningSession
from .scoring import ScoredItem, calculate_risk


def active_questions():
    return list(Question.objects.filter(is_active=True).order_by("number"))


def validate_age(age):
    try:
        age = int(age)
    except (TypeError, ValueError):
        raise ValidationError({"child_age_months": ["Enter your child's age in months, as a number."]})
    if not MIN_AGE_MONTHS <= age <= MAX_AGE_MONTHS:
        raise ValidationError({"child_age_months": [AGE_MESSAGE]})
    return age


def submit_screening(child_age_months, answers):
    """Save an anonymous screening and its result.

    answers: {question_id: bool}. Every active question must be answered.
    Returns (session, result, raw_token). Raises ValidationError with
    plain-language messages.
    """
    age = validate_age(child_age_months)
    questions = active_questions()
    by_id = {q.id: q for q in questions}

    unknown = set(answers) - set(by_id)
    if unknown:
        raise ValidationError({"answers": ["Some answers don't match the current questionnaire. Please reload."]})
    missing = [q.number for q in questions if q.id not in answers]
    if missing:
        raise ValidationError(
            {"answers": [f"Please answer every question. Still to answer: {', '.join(map(str, missing))}."]}
        )

    score, tier = calculate_risk(
        ScoredItem(value=answers[q.id], weight=q.weight, is_reverse_scored=q.is_reverse_scored)
        for q in questions
    )

    token, token_hash = ScreeningSession.new_token()
    with transaction.atomic():
        session = ScreeningSession.objects.create(anonymous_token_hash=token_hash, child_age_months=age)
        Answer.objects.bulk_create(
            [Answer(session=session, question=q, value=answers[q.id]) for q in questions]
        )
        result = RiskResult.objects.create(session=session, score=score, tier=tier)
    return session, result, token
