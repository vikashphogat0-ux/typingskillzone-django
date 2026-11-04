from django.contrib import admin
from accounts.admin_permissions import SuperAdminOnlyAdminMixin
from .models import LearnerProfile


@admin.register(LearnerProfile)
class LearnerProfileAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "display_name",
        "user",
        "preferred_language",
        "target_wpm",
        "target_accuracy",
        "onboarding_completed",
    )
    list_filter = ("preferred_language", "onboarding_completed")
    search_fields = ("display_name", "user__email")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Account", {"fields": ("user", "display_name")}),
        ("Learning preferences", {
            "fields": (
                "preferred_language",
                "preferred_script",
                "target_wpm",
                "target_accuracy",
                "daily_practice_goal_minutes",
                "timezone",
                "onboarding_completed",
            )
        }),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
