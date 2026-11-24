from django.contrib import admin

from .models import Attempt, Flashcard, Learner, LearningSession, TeacherProfile


@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ["symbol", "label", "difficulty", "category", "source", "is_active"]
    list_filter = ["difficulty", "category", "source", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["label"]


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ["full_name", "school_name", "user"]
    search_fields = ["full_name", "school_name", "user__email"]


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ["nickname", "teacher", "current_level", "created_at"]
    list_filter = ["current_level"]


class AttemptInline(admin.TabularInline):
    model = Attempt
    extra = 0
    can_delete = False
    readonly_fields = ["number", "flashcard", "chosen_label", "is_correct", "response_time_ms", "level", "level_after"]


@admin.register(LearningSession)
class LearningSessionAdmin(admin.ModelAdmin):
    list_display = ["learner", "teacher", "started_at", "start_level", "end_level", "total_attempts",
                    "correct_count", "ai_status"]
    list_filter = ["ai_status", "sensory_mode"]
    inlines = [AttemptInline]
    readonly_fields = [f.name for f in LearningSession._meta.fields]
