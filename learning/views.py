"""Teacher pages: register, classroom dashboard, learners, session setup, play, summary."""
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render

from . import ai
from .forms import LearnerForm, SessionSettingsForm, TeacherRegisterForm
from .models import LearningSession, TeacherProfile
from .permissions import teacher_required
from .services import start_session


def teacher_register(request):
    form = TeacherRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        User = get_user_model()
        user = User(email=User.objects.normalize_email(d["email"]), role=User.Role.TEACHER)
        try:
            validate_password(d["password"], user=user)
        except ValidationError as e:
            for msg in e.messages:
                form.add_error("password", msg)
        else:
            with transaction.atomic():
                user.set_password(d["password"])
                user.save()
                TeacherProfile.objects.create(user=user, full_name=d["full_name"], school_name=d["school_name"])
            login(request, user, backend="accounts.backends.LockoutBackend")
            messages.success(request, "Account created. Add your first learner to begin.")
            return redirect("teach")
    return render(request, "learning/register.html", {"form": form})


@teacher_required
def classroom(request):
    teacher = request.teacher
    form = LearnerForm(request.POST or None, teacher=teacher, initial={"current_level": 1})
    if request.method == "POST" and form.is_valid():
        learner = form.save(commit=False)
        learner.teacher = teacher
        learner.save()
        messages.success(request, f"{learner.nickname} has been added.")
        return redirect("teach")
    learners = teacher.learners.annotate(
        session_count=Count("sessions"), last_session=Max("sessions__started_at")
    )
    recent = teacher.sessions.select_related("learner").filter(ended_at__isnull=False)[:8]
    return render(request, "learning/classroom.html", {
        "teacher": teacher, "learners": learners, "recent": recent, "form": form,
        "ai_configured": ai.is_configured(),
    })


@teacher_required
def learner_remove(request, pk):
    learner = get_object_or_404(request.teacher.learners, pk=pk)
    if request.method == "POST":
        learner.delete()
        messages.success(request, f"{learner.nickname} and their sessions have been removed.")
    return redirect("teach")


@teacher_required
def session_setup(request, pk):
    learner = get_object_or_404(request.teacher.learners, pk=pk)
    form = SessionSettingsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        session = start_session(request.teacher, learner, **form.cleaned_data)
        return redirect("teach-play", pk=session.pk)
    return render(request, "learning/session_setup.html", {
        "learner": learner, "form": form, "ai_configured": ai.is_configured(),
    })


@teacher_required
def play(request, pk):
    session = get_object_or_404(request.teacher.sessions.select_related("learner"), pk=pk)
    if session.is_finished:
        return redirect("teach-summary", pk=session.pk)
    return render(request, "learning/play.html", {"session": session})


@teacher_required
def summary(request, pk):
    session = get_object_or_404(request.teacher.sessions.select_related("learner"), pk=pk)
    attempts = session.attempts.select_related("flashcard")
    avg_ms = round(sum(a.response_time_ms for a in attempts) / len(attempts)) if attempts else None
    return render(request, "learning/summary.html", {
        "session": session, "attempts": attempts, "avg_seconds": round(avg_ms / 1000, 1) if avg_ms else None,
    })
