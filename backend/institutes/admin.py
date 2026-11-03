from django.contrib import admin, messages
from django.utils import timezone

from .models import Institute, InstituteMembership


class InstituteMembershipInline(admin.TabularInline):
    model = InstituteMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "registration_code",
        "owner",
        "email",
        "city",
        "state",
        "status",
        "created_at",
    )
    list_filter = ("status", "state", "created_at")
    search_fields = (
        "name",
        "registration_code",
        "email",
        "phone",
        "owner__email",
        "city",
    )
    readonly_fields = (
        "id",
        "registration_code",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    )
    inlines = (InstituteMembershipInline,)
    ordering = ("-created_at",)
    actions = ("approve_selected", "reject_selected", "suspend_selected")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            for action_name in self.actions:
                actions.pop(action_name, None)
        return actions

    @admin.action(description="Approve selected institute applications")
    def approve_selected(self, request, queryset):
        updated = queryset.filter(status=Institute.Status.PENDING).update(
            status=Institute.Status.APPROVED,
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(
            request,
            f"{updated} pending institute application(s) approved.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Reject selected institute applications")
    def reject_selected(self, request, queryset):
        updated = queryset.filter(status=Institute.Status.PENDING).update(
            status=Institute.Status.REJECTED,
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(
            request,
            f"{updated} pending institute application(s) rejected.",
            level=messages.WARNING,
        )

    @admin.action(description="Suspend selected approved institutes")
    def suspend_selected(self, request, queryset):
        updated = queryset.filter(status=Institute.Status.APPROVED).update(
            status=Institute.Status.SUSPENDED,
        )
        self.message_user(
            request,
            f"{updated} approved institute(s) suspended.",
            level=messages.WARNING,
        )


@admin.register(InstituteMembership)
class InstituteMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "institute",
        "user",
        "role",
        "is_active",
        "joined_at",
    )
    list_filter = ("role", "is_active", "institute")
    search_fields = ("institute__name", "user__email")
    readonly_fields = ("joined_at",)
    autocomplete_fields = ("institute", "user")
