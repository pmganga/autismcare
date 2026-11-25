"""Screening module models, following the SRS class diagram (Appendix B.2).

Privacy (NFR 4): a ScreeningSession holds no personally identifiable
information. There is no name, email, phone, IP address or user link. Only
the child's age in months is kept, because scoring depends on it.
"""
import hashlib
import secrets
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Question(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    text = models.CharField(max_length=500)
    weight = models.PositiveSmallIntegerField(default=1)
    is_reverse_scored = models.BooleanField(
        default=False,
        help_text="If ticked, a 'Yes' answer is the risk answer. Otherwise 'No' is.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number}. {self.text[:60]}"


class RiskTier(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class ScreeningSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Only a hash is stored. The raw token is given to the parent once, and
    # anyone holding it can view the result again.
    anonymous_token_hash = models.CharField(max_length=64, editable=False)
    child_age_months = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(16), MaxValueValidator(30)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Screening {str(self.id)[:8]} ({self.created_at:%Y-%m-%d})"

    @staticmethod
    def new_token():
        token = secrets.token_urlsafe(24)
        return token, hash_token(token)

    def token_matches(self, token):
        return bool(token) and secrets.compare_digest(self.anonymous_token_hash, hash_token(token))


class Answer(models.Model):
    session = models.ForeignKey(ScreeningSession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="+")
    value = models.BooleanField(help_text="True = Yes, False = No")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "question"], name="one_answer_per_question")]


class RiskResult(models.Model):
    session = models.OneToOneField(ScreeningSession, on_delete=models.CASCADE, related_name="result")
    score = models.PositiveSmallIntegerField()
    tier = models.CharField(max_length=6, choices=RiskTier.choices)
    calculated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_tier_display()} ({self.score})"


class GuidanceReport(models.Model):
    """FR 2.2: record of the PDF guidance report (class diagram: GuidanceReport).

    The PDF itself is generated on demand from the stored answers, so no file
    containing health data is kept on disk.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.OneToOneField(RiskResult, on_delete=models.CASCADE, related_name="report")
    next_steps = models.TextField()
    generated_at = models.DateTimeField(auto_now_add=True)
    download_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Report {str(self.id)[:8]}"
