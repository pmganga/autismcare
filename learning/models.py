"""AI teaching assistant models (SRS FR 4.1, FR 4.2; class diagram B.2).

Class diagram mapping:
  Teacher         -> TeacherProfile (a User with role TEACHER, plus school name)
  Learner         -> Learner (nickname only, no personal data, current level)
  LearningSession -> LearningSession (sensory mode, audio, progress summary)
  Attempt         -> Attempt (is correct, response time)
  Flashcard       -> Flashcard (image, label, difficulty)
  AdaptiveEngine  -> learning/engine.py
"""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

MIN_LEVEL, MAX_LEVEL = 1, 5
LEVEL_VALIDATORS = [MinValueValidator(MIN_LEVEL), MaxValueValidator(MAX_LEVEL)]


class TeacherProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile")
    full_name = models.CharField(max_length=150)
    school_name = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.full_name} ({self.school_name})"


class Learner(models.Model):
    """A child in the teacher's class. Nickname only, by design (privacy)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="learners")
    nickname = models.CharField(max_length=40, help_text="A first name or nickname only. No surnames.")
    current_level = models.PositiveSmallIntegerField(default=1, validators=LEVEL_VALIDATORS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nickname"]
        constraints = [models.UniqueConstraint(fields=["teacher", "nickname"], name="unique_nickname_per_teacher")]

    def __str__(self):
        return self.nickname


class Flashcard(models.Model):
    class Category(models.TextChoices):
        ANIMALS = "animals", "Animals"
        FOOD = "food", "Food"
        TRANSPORT = "transport", "Transport"
        HOME = "home", "Home and school"
        NATURE = "nature", "Nature"
        CLOTHES = "clothes", "Clothes"

    class Source(models.TextChoices):
        BUILTIN = "BUILTIN", "Built-in"
        AI = "AI", "AI-generated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=40, unique=True)
    symbol = models.CharField(max_length=16, help_text="The picture shown on the card (an emoji).")
    image_url = models.URLField(blank=True, help_text="Optional photo; used instead of the symbol if set.")
    difficulty = models.PositiveSmallIntegerField(validators=LEVEL_VALIDATORS)
    category = models.CharField(max_length=12, choices=Category.choices)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.BUILTIN)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["difficulty", "label"]

    def __str__(self):
        return f"{self.symbol} {self.label} (level {self.difficulty})"


class LearningSession(models.Model):
    class SensoryMode(models.TextChoices):
        SOFT = "soft", "Soft colours (default)"
        CONTRAST = "contrast", "High contrast"
        DIM = "dim", "Dim (dark background)"

    class AIStatus(models.TextChoices):
        OFF = "off", "AI not configured"
        USED = "used", "AI cards added"
        UNAVAILABLE = "unavailable", "AI unavailable, used built-in cards"
        PENDING = "pending", "AI cards being generated in the background"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="sessions")
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Sensory settings (activity diagram: "Configure sensory settings")
    sensory_mode = models.CharField(max_length=10, choices=SensoryMode.choices, default=SensoryMode.SOFT)
    audio_enabled = models.BooleanField(default=True)
    planned_cards = models.PositiveSmallIntegerField(default=9)

    # Progress
    start_level = models.PositiveSmallIntegerField(validators=LEVEL_VALIDATORS)
    current_level = models.PositiveSmallIntegerField(validators=LEVEL_VALIDATORS)
    end_level = models.PositiveSmallIntegerField(null=True, blank=True)
    total_attempts = models.PositiveSmallIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    attempts_since_check = models.PositiveSmallIntegerField(default=0)

    # The card currently on screen, so answers are checked on the server
    current_card = models.ForeignKey(Flashcard, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    current_choices = models.JSONField(default=list, blank=True)
    shown_at = models.DateTimeField(null=True, blank=True)

    # AI/NLP service (activity diagram: "Generate flashcard set for that level")
    ai_status = models.CharField(max_length=12, choices=AIStatus.choices, default=AIStatus.OFF)
    ai_cards_added = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.learner} – {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def is_finished(self):
        return self.ended_at is not None

    @property
    def accuracy_percent(self):
        return round(100 * self.correct_count / self.total_attempts) if self.total_attempts else None


class Attempt(models.Model):
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="attempts")
    flashcard = models.ForeignKey(Flashcard, on_delete=models.PROTECT, related_name="+")
    number = models.PositiveSmallIntegerField()
    chosen_label = models.CharField(max_length=40)
    is_correct = models.BooleanField()
    response_time_ms = models.PositiveIntegerField()
    level = models.PositiveSmallIntegerField()
    level_after = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["session", "number"], name="unique_attempt_number")]
