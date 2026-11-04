from django.contrib import admin

from accounts.admin_permissions import SuperAdminOnlyAdminMixin

from .models import TypingSession


@admin.register(TypingSession)
class TypingSessionAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "learner", "publication", "state", "started_at", "completed_at")
    list_filter = ("state",)
    search_fields = ("learner__email", "publication__exam__code")
    readonly_fields = (
        "id", "learner", "publication", "state", "started_at", "deadline_at",
        "completed_at", "duration_seconds", "reference_text", "submitted_text",
        "rules_snapshot", "scoring_version", "result_snapshot",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
