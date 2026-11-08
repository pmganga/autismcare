from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .backends import is_locked
from .forms import LoginForm, RegisterForm
from .services import INVALID_MESSAGE, LOCKED_MESSAGE, register_therapist


def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            user = register_therapist(
                email=d["email"], password=d["password"], full_name=d["full_name"], phone=d["phone"]
            )
        except ValidationError as e:
            for msg in e.messages:
                form.add_error("password", msg)
        else:
            login(request, user, backend="accounts.backends.LockoutBackend")
            messages.success(request, "Account created. Next, add your clinic and upload your licence.")
            return redirect("dashboard")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = authenticate(request, email=email, password=form.cleaned_data["password"])
        if user is not None:
            login(request, user)
            return redirect(request.GET.get("next") or "dashboard")
        form.add_error(None, LOCKED_MESSAGE if is_locked(email) else INVALID_MESSAGE)
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")
