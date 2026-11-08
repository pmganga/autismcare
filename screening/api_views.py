"""Screening REST endpoints (FR 1.1, FR 2.1). No login required (NFR 4)."""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .content import DISCLAIMER, MAX_AGE_MONTHS, MIN_AGE_MONTHS, TIER_GUIDANCE
from .models import ScreeningSession
from .services import active_questions, submit_screening


def result_payload(session, result):
    g = TIER_GUIDANCE[result.tier]
    return {
        "session_id": str(session.id),
        "score": result.score,
        "tier": result.tier,
        "heading": g["heading"],
        "summary": g["summary"],
        "next_steps": g["next_steps"],
        "calculated_at": result.calculated_at,
        "disclaimer": DISCLAIMER,
    }


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
        session = get_object_or_404(ScreeningSession.objects.select_related("result"), pk=pk)
        if not session.token_matches(request.query_params.get("token", "")):
            # Same response as "not found", so IDs can't be probed.
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(result_payload(session, session.result))
