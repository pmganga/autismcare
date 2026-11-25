"""Email and password login. Locks the account after 5 wrong passwords (FR 1.2).

Used by the API, the web pages and the admin panel.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import F


class LockoutBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get("email") or username
        if not email or password is None:
            return None

        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Check a password anyway, so the reply takes the same time for unknown emails.
            User().set_password(password)
            return None

        if user.is_locked:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            if user.failed_login_attempts:
                User.objects.filter(pk=user.pk).update(failed_login_attempts=0)
            return user

        # Wrong password: add one to the count and lock at the limit.
        User.objects.filter(pk=user.pk).update(failed_login_attempts=F("failed_login_attempts") + 1)
        user.refresh_from_db(fields=["failed_login_attempts"])
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            User.objects.filter(pk=user.pk).update(is_locked=True)
        return None


def is_locked(email):
    User = get_user_model()
    return User.objects.filter(email__iexact=email or "", is_locked=True).exists()
