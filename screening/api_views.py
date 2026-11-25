"""Screening REST endpoints (FR 1.1, FR 2.1). No login required (NFR 4)."""
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .content import DISCLAIMER, MAX_AGE_MONTHS, MIN_AGE_MONTHS, TIER_GUIDANCE
from .models import ScreeningSession
from .report import build_pdf, report_filename
from .rescreen import rescreen_advice
from .services import active_questions, submit_screening


def result_payload(session, result):
    g = TIER_GUIDANCE[result.tier]
    advice = rescreen_advice(
        session.child_age_months, result.tier, timezone.localtime(result.calculated_at).date()
    )
    return {
        "session_id": str(session.id),
        "score": result.score,
        "tier": result.tier,
        "heading": g["heading"],
        "summary": g["summary"],
        "next_steps": g["next_steps"],
        "rescreen": {"due": advice.due, "text": advice.text},
        "refer_to_directory": result.tier == "HIGH",
        "calculated_at": result.calculated_at,
        "disclaimer": DISCLAIMER,
    }


def _session_for_token(request, pk):
    session = get_object_or_404(ScreeningSession.objects.select_related("result"), pk=pk)
    if not session.token_matches(request.query_params.get("token", "")):
        # Same response as "not found", so IDs can't be probed.
        raise Http404
    return session


class QuestionnaireView(APIView):
    """GET /api/screening/questionnaire/"""

    def get(self, request):
        return Response({
            "disclaimer": DISCLAIMER,
            "age_range_months": [MIN_AGE_MONTHS, MAX_AGE_MONTHS],
            "questions": [{"id": q.id, "number": q.number, "text": q.text} for q in active_questions()],
        })


class AnswerSerializer(serializers.Serializer):
    question = serializers.IntegerField()
    value = serializers.BooleanField()


class SubmitSerializer(serializers.Serializer):
    child_age_months = serializers.IntegerField()
    answers = AnswerSerializer(many=True)


class ScreeningCreateView(APIView):
    """POST /api/screenings/  {child_age_months, answers: [{question, value}]}

    Returns the result plus a one-time `token`. Keep it to view the result again.
    """

    def post(self, request):
        s = SubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        answers = {a["question"]: a["value"] for a in s.validated_data["answers"]}
        try:
            session, result, token = submit_screening(s.validated_data["child_age_months"], answers)
        except ValidationError as e:
            return Response(e.message_dict, status=status.HTTP_400_BAD_REQUEST)
        return Response({**result_payload(session, result), "token": token}, status=status.HTTP_201_CREATED)


class ScreeningResultView(APIView):
    """GET /api/screenings/<id>/?token=<token>"""

    def get(self, request, pk):
        session = _session_for_token(request, pk)
        return Response(result_payload(session, session.result))


class ScreeningReportView(APIView):
    """GET /api/screenings/<id>/report/?token=<token>  ->  PDF (FR 2.2)"""

    def get(self, request, pk):
        session = _session_for_token(request, pk)
        pdf, _ = build_pdf(session, directory_url=request.build_absolute_uri(reverse("find")))
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_filename(session)}"'
        return response
