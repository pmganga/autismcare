"""Shared logic for the API and the web pages."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from directory.models import Therapist


@transaction.atomic
def register_therapist(*, email, password, full_name, phone):
    """Create a therapist account and its empty profile.

    Raises django.core.exceptions.ValidationError if the password is too weak.
    """
    User = get_user_model()
    user = User(email=User.objects.normalize_email(email), role=User.Role.THERAPIST)
    validate_password(password, user=user)  # 12-character minimum (FR 1.2)
    user.set_password(password)
    user.save()
    Therapist.objects.create(user=user, full_name=full_name, phone=phone)
    return user


LOCKED_MESSAGE = (
    "This account is locked after 5 failed login attempts. "
    "Please contact an AutismCare administrator to unlock it."
)
INVALID_MESSAGE = "Incorrect email or password."
