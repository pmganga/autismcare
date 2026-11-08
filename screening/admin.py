from django.contrib import admin

from .models import Answer, Question, RiskResult, ScreeningSession


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["number", "text", "weight", "is_reverse_scored", "is_active"]
    list_editable = ["is_active"]
    list_filter = ["is_active", "is_reverse_scored"]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    can_delete = False
    readonly_fields = ["question", "value"]

    def has_add_permission(self, request, obj=None):
        return False


class ResultInline(admin.StackedInline):
    model = RiskResult
    can_delete = False
    readonly_fields = ["score", "tier", "calculated_at"]


@admin.register(ScreeningSession)
class ScreeningSessionAdmin(admin.ModelAdmin):
    """Read-only, anonymous records for monitoring totals per tier."""

    list_display = ["id", "child_age_months", "tier", "score", "created_at"]
    list_filter = ["result__tier", "created_at"]
    readonly_fields = ["id", "child_age_months", "created_at"]
    exclude = ["anonymous_token_hash"]
    inlines = [ResultInline, AnswerInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Tier", ordering="result__tier")
    def tier(self, obj):
        return obj.result.get_tier_display() if hasattr(obj, "result") else "—"

    @admin.display(description="Score", ordering="result__score")
    def score(self, obj):
        return obj.result.score if hasattr(obj, "result") else "—"
