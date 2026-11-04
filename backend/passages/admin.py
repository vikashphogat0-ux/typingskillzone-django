from django.contrib import admin, messages

from accounts.admin_permissions import SuperAdminOnlyAdminMixin
from .models import ExamPassageSequence, PassageSource, SimulatorPassage
from .services import publish_source_to_selected_exams


@admin.register(PassageSource)
class PassageSourceAdmin(SuperAdminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("title", "language", "script", "status", "target_count", "created_at")
    list_filter = ("status", "language", "script", "target_exams")
    search_fields = ("title", "content", "source_reference")
    filter_horizontal = ("target_exams",)
    readonly_fields = ("created_by", "created_at", "updated_at")
    actions = ("publish_selected_sources",)
    fieldsets = (
        ("Central source passage", {"fields": ("title", "content", "language", "script", "source_reference")}),
        ("Distribution", {"fields": ("target_exams", "status")}),
        ("Ownership", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    @admin.display(description="Target simulators")
    def target_count(self, obj):
        return obj.target_exams.count()

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
    list_display = ("passage_id", "exam", "source", "status", "published_at")
    list_filter = ("exam", "status", "source__language")
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
