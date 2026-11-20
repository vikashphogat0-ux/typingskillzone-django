from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import path
from django.utils.html import format_html

from accounts.admin_permissions import SuperAdminOnlyAdminMixin
from .models import ExamPassageSequence, PassageSource, SimulatorPassage
from .services import auto_target_and_publish, matching_exams, publish_source_to_selected_exams


@admin.register(PassageSource)
class PassageSourceAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("title", "language", "script", "status", "target_count", "created_at", "preview_link")
    list_filter = ("status", "language", "script", "target_exams")
    search_fields = ("title", "content", "source_reference")
    filter_horizontal = ("target_exams",)
    readonly_fields = ("created_by", "created_at", "updated_at")
    actions = ("publish_selected_sources", "publish_to_matching_exams")
    fieldsets = (
        ("Central source passage", {"fields": ("title", "content", "language", "script", "source_reference")}),
        ("Distribution", {"fields": ("target_exams", "status")}),
        ("Ownership", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    @admin.display(description="Target simulators")
    def target_count(self, obj):
        return obj.target_exams.count()

    @admin.display(description="Preview")
    def preview_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:passages_preview", args=[obj.pk])
        return format_html('<a href="{}">View in each exam</a>', url)

    def get_urls(self):
        custom = [
            path("studio/", self.admin_site.admin_view(self.studio_view), name="passages_studio"),
            path("<int:object_id>/preview/", self.admin_site.admin_view(self.preview_view), name="passages_preview"),
        ]
        return custom + super().get_urls()

    def _require_superuser(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied

    def preview_view(self, request, object_id):
        """Show the passage as each matching exam will display it. Read-only."""
        from .models import SimulatorPassage

        self._require_superuser(request)
        source = get_object_or_404(PassageSource, pk=object_id)
        rows = []
        for exam in matching_exams(source):
            passage = SimulatorPassage(exam=exam, source=source, serial_number=0)
            rows.append({
                "exam": exam,
                "layout": exam.get_passage_layout_display(),
                "configured": exam.passage_layout != exam.PassageLayout.UNCONFIGURED,
                "targeted": source.target_exams.filter(pk=exam.pk).exists(),
                "paragraphs": passage.rendered_paragraphs,
            })
        context = dict(self.admin_site.each_context(request), source=source, rows=rows, title="Preview")
        return render(request, "admin/passages/preview.html", context)

    def studio_view(self, request):
        """Passage studio: layout status and publication counts for every active exam. Read-only."""
        from exams.models import ExamConfiguration
        from .models import SimulatorPassage

        self._require_superuser(request)
        exams = []
        for exam in ExamConfiguration.objects.filter(is_active=True).order_by("language", "name"):
            published = SimulatorPassage.objects.filter(exam=exam, status=SimulatorPassage.Status.PUBLISHED)
            latest = published.order_by("-published_at").first()
            exams.append({
                "exam": exam,
                "layout": exam.get_passage_layout_display(),
                "configured": exam.passage_layout != exam.PassageLayout.UNCONFIGURED,
                "published": published.count(),
                "latest": latest.published_at if latest else None,
                "ready_drafts": PassageSource.objects.filter(
                    status=PassageSource.Status.DRAFT, language__iexact=exam.language
                ).count(),
            })
        context = dict(
            self.admin_site.each_context(request),
            exams=exams,
            draft_count=PassageSource.objects.filter(status=PassageSource.Status.DRAFT).count(),
            published_count=PassageSource.objects.filter(status=PassageSource.Status.PUBLISHED).count(),
            unconfigured_count=sum(1 for row in exams if not row["configured"]),
            empty_count=sum(1 for row in exams if row["published"] == 0),
            title="Passage studio",
        )
        return render(request, "admin/passages/studio.html", context)

    @admin.action(description="Publish to ALL matching exams (auto-target by language and script)")
    def publish_to_matching_exams(self, request, queryset):
        total = 0
        failures = []
        for source in queryset:
            try:
                total += len(auto_target_and_publish(source))
            except ValueError as exc:
                failures.append(f"{source.title}: {exc}")
        if total:
            self.message_user(request, f"Published to {total} matching exam(s).", messages.SUCCESS)
        for failure in failures:
            self.message_user(request, failure, messages.ERROR)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        source = form.instance
        if source.status == PassageSource.Status.PUBLISHED:
            try:
                created = publish_source_to_selected_exams(source)
            except ValueError as exc:
                source.status = PassageSource.Status.DRAFT
                source.save(update_fields=("status", "updated_at"))
                self.message_user(request, str(exc), level=messages.ERROR)
                return
            self.message_user(
                request,
                f"Published to {len(created)} selected simulator(s). Existing publications keep their passage IDs.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Publish selected central passages to their selected simulators")
    def publish_selected_sources(self, request, queryset):
        count = 0
        failures = []
        for source in queryset.prefetch_related("target_exams"):
            try:
                count += len(publish_source_to_selected_exams(source))
            except ValueError as exc:
                failures.append(f"{source.title}: {exc}")
        if count:
            self.message_user(request, f"Published or confirmed {count} simulator publication(s).", messages.SUCCESS)
        for failure in failures:
            self.message_user(request, failure, messages.ERROR)


@admin.register(SimulatorPassage)
class SimulatorPassageAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("passage_id", "exam", "source", "status", "release_date", "release_slot", "release_position")
    list_filter = ("exam", "status", "release_slot", "source__language")
    search_fields = ("source__title", "source__content", "exam__name")
    readonly_fields = ("exam", "source", "serial_number", "status", "published_at", "created_at")
    ordering = ("exam", "serial_number")

    actions = ("archive_publications",)

    @admin.action(description="Archive selected simulator publications (IDs are retained)")
    def archive_publications(self, request, queryset):
        updated = queryset.exclude(status=SimulatorPassage.Status.ARCHIVED).update(
            status=SimulatorPassage.Status.ARCHIVED
        )
        self.message_user(request, f"Archived {updated} publication(s). Their IDs will never be reused.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExamPassageSequence)
class ExamPassageSequenceAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("exam", "next_number", "updated_at")
    readonly_fields = ("exam", "next_number", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
