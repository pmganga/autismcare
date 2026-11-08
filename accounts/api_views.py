"""REST endpoints: /api/auth/register/, /api/auth/login/, /api/auth/logout/"""
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .backends import is_locked
from .serializers import LoginSerializer, RegisterSerializer
from .services import INVALID_MESSAGE, LOCKED_MESSAGE, register_therapist


class RegisterView(APIView):
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            user = register_therapist(**s.validated_data)
        except DjangoValidationError as e:
            return Response({"password": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user_id": str(user.id)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"]
        user = authenticate(request, email=email, password=s.validated_data["password"])
        if user is None:
            if is_locked(email):
                return Response({"detail": LOCKED_MESSAGE}, status=status.HTTP_423_LOCKED)
            return Response({"detail": INVALID_MESSAGE}, status=status.HTTP_401_UNAUTHORIZED)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "role": user.role})


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
