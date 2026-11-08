from rest_framework.permissions import BasePermission


class IsTherapist(BasePermission):
    message = "Only therapist accounts can do this."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and hasattr(request.user, "therapist_profile")
        )
