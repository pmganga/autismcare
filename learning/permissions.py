from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from rest_framework.permissions import BasePermission


def get_teacher(user):
    return getattr(user, "teacher_profile", None) if user.is_authenticated else None


def teacher_required(view):
    """Login required, and the account must be a teacher account."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        teacher = get_teacher(request.user)
        if teacher is None:
            messages.info(request, "The teaching assistant is for teacher accounts.")
            return redirect("home")
        request.teacher = teacher
        return view(request, *args, **kwargs)

    return wrapper


class IsTeacher(BasePermission):
    message = "Only teacher accounts can do this."

    def has_permission(self, request, view):
        return get_teacher(request.user) is not None
