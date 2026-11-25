"""JSON endpoints for the play screen. Teachers can only use their own sessions."""
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsTeacher
from .services import SessionError, answer, finish_session, next_card


class _SessionView(APIView):
    permission_classes = [IsTeacher]

    def get_session(self, request, pk):
        return get_object_or_404(request.user.teacher_profile.sessions, pk=pk)


class NextCardView(_SessionView):
    """POST /api/learning/sessions/<id>/next/ -> the card to show, or {"done": true}."""

    def post(self, request, pk):
        session = self.get_session(request, pk)
        try:
            card = next_card(session)
        except SessionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        if card is None:
            finish_session(session)
            return Response({"done": True})
        return Response({"done": False, "card": card})


class AnswerSerializer(serializers.Serializer):
    choice = serializers.CharField(max_length=40)
    response_time_ms = serializers.IntegerField(required=False, min_value=0)


class AnswerView(_SessionView):
    """POST /api/learning/sessions/<id>/answer/ {choice, response_time_ms}"""

    def post(self, request, pk):
        session = self.get_session(request, pk)
        s = AnswerSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = answer(session, s.validated_data["choice"], s.validated_data.get("response_time_ms"))
        except SessionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class EndSessionView(_SessionView):
    """POST /api/learning/sessions/<id>/end/ -> teacher ends the session early."""

    def post(self, request, pk):
        session = finish_session(self.get_session(request, pk))
        return Response({"done": True, "summary_url": reverse("teach-summary", args=[session.pk])})
