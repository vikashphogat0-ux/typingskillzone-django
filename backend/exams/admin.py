from django.contrib import admin
from accounts.admin_permissions import SuperAdminOnlyAdminMixin
from .models import ExamConfiguration


@admin.register(ExamConfiguration)
class ExamConfigurationAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "category", "language", "script", "duration_seconds", "verification_status", "is_active")
    list_filter = ("category", "language", "script", "verification_status", "is_active", "passage_format")
    search_fields = ("name", "code", "official_source_url", "source_title")
    ordering = ("category", "display_order", "name")
    list_editable = ("verification_status", "is_active")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Identity", {"fields": ("name", "code", "category", "display_order", "is_active")}),
        ("Typing interface", {"fields": ("language", "script", "interface_type", "duration_seconds", "passage_format", "passage_word_limit")}),
        ("Input and scoring rules", {"fields": ("allow_backspace", "allow_arrow_navigation", "error_rules", "scoring_rules", "qualification_rules")}),
        ("Official rule verification", {"fields": ("verification_status", "official_source_url", "source_title", "source_checked_at", "rule_notes")}),
        ("System timestamps", {"fields": ("created_at", "updated_at")}),
    )

    prepopulated_fields = {"code": ("name",)}
