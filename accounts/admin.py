from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "role", "is_locked", "failed_login_attempts", "is_staff", "date_joined"]
    list_filter = ["role", "is_locked", "is_staff"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["failed_login_attempts", "last_login", "date_joined"]
    actions = ["unlock_accounts"]

    fieldsets = (
        (None, {"fields": ("email", "password", "role")}),
        ("Lockout (FR 1.2)", {"fields": ("is_locked", "failed_login_attempts")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),
    )

    @admin.action(description="Unlock selected accounts")
    def unlock_accounts(self, request, queryset):
        n = queryset.update(is_locked=False, failed_login_attempts=0)
        self.message_user(request, f"Unlocked {n} account(s).")
