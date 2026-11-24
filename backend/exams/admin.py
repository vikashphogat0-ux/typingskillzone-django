from django.contrib import admin
from django.utils.html import format_html, format_html_join

from accounts.admin_permissions import SuperAdminOnlyAdminMixin
from .configuration_audit import audit_exam_configuration
from .models import ExamConfiguration


@admin.register(ExamConfiguration)
class ExamConfigurationAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "name", "code", "category", "language", "script", "backspace_policy",
        "scoring_mode", "passage_layout", "configuration_readiness",
        "presentation_reference_status", "verification_status", "is_active",
    )
    list_filter = (
        "category", "language", "script", "verification_status",
        "presentation_reference_status", "passage_layout", "is_active",
    )
    search_fields = (
        "name", "code", "official_source_url", "source_title",
        "presentation_reference_title", "presentation_reference_url",
    )
    ordering = ("category", "display_order", "name")
    list_editable = ("presentation_reference_status", "verification_status", "is_active")
    readonly_fields = ("configuration_audit", "created_at", "updated_at")
    fieldsets = (
        ("Identity", {"fields": ("name", "code", "category", "display_order", "is_active")}),
        ("Typing interface", {"fields": ("language", "script", "interface_type", "duration_seconds", "passage_format", "passage_word_limit")}),
        ("Exam-specific passage presentation", {"fields": ("passage_layout", "passage_font_family", "passage_font_size_pt", "passage_line_height", "passage_paragraph_spacing_pt", "passage_alignment", "passage_first_line_indent_em", "passage_preserve_tabs", "passage_tab_size")}),
        ("Presentation reference (separate from official exam rules)", {"fields": ("presentation_reference_status", "presentation_reference_url", "presentation_reference_title", "presentation_reference_checked_at", "presentation_notes")}),
        ("Keyboard and editing behaviour", {"fields": (
            "backspace_policy", "allow_backspace", "allow_delete", "allow_arrow_navigation",
            "allow_paste", "allow_copy", "allow_cut", "enter_behavior", "space_behavior",
            "tab_behavior", "keyboard_layout", "text_encoding",
        )}),
        ("Timing and typing targets", {"fields": (
            "minimum_wpm", "required_keystrokes", "strokes_per_word", "trial_seconds",
            "review_seconds", "correction_seconds", "transcription_seconds",
            "allow_passage_repeat", "passage_source_mode",
        )}),
        ("Scoring and qualification rules", {"fields": (
            "scoring_mode", "error_allowance_percent", "mistake_penalty_strokes",
            "error_rules", "scoring_rules", "qualification_rules", "rule_config_version",
        )}),
        ("Official rule verification", {"fields": ("verification_status", "official_source_url", "source_title", "source_checked_at", "rule_notes")}),
        ("Configuration readiness audit", {"fields": ("configuration_audit",)}),
        ("System timestamps", {"fields": ("created_at", "updated_at")}),
    )

    prepopulated_fields = {"code": ("name",)}

    @admin.display(description="Rule configuration")
    def configuration_readiness(self, obj):
        audit = audit_exam_configuration(obj)
        if audit["ready"]:
            return format_html('<strong style="color: #16803c">READY</strong>')
        return format_html(
            '<strong style="color: #b45309">INCOMPLETE ({})</strong>',
            len(audit["errors"]),
        )

    @admin.display(description="Readiness audit")
    def configuration_audit(self, obj):
        if not obj or not obj.pk:
            return "Save this profile to run its configuration audit."
        audit = audit_exam_configuration(obj)
        status = "READY" if audit["ready"] else "DRAFT — INCOMPLETE"
        errors = format_html_join("", "<li>{}</li>", ((item,) for item in audit["errors"]))
        warnings = format_html_join("", "<li>{}</li>", ((item,) for item in audit["warnings"]))
        return format_html(
            "<p><strong>Status:</strong> {}</p><p><strong>Blocking issues ({})</strong></p><ul>{}</ul>"
            "<p><strong>Warnings ({})</strong></p><ul>{}</ul>",
            status, len(audit["errors"]), errors or format_html("<li>None</li>"),
            len(audit["warnings"]), warnings or format_html("<li>None</li>"),
        )
