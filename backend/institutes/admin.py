from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import Institute, InstituteMembership, InstituteSubscription, SubscriptionPlan
from .views import start_free_trial


class InstituteMembershipInline(admin.TabularInline):
    model = InstituteMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ("name", "registration_code", "owner", "email", "city", "state", "status", "created_at")
    list_filter = ("status", "state", "created_at")
    search_fields = ("name", "registration_code", "email", "phone", "owner__email", "city")
    readonly_fields = ("id", "registration_code", "approved_by", "approved_at", "created_at", "updated_at")
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
        approved = 0
        with transaction.atomic():
            pending_institutes = queryset.select_for_update().filter(
                status=Institute.Status.PENDING
            )
            for institute in pending_institutes:
                institute.status = Institute.Status.APPROVED
                institute.approved_by = request.user
                institute.approved_at = timezone.now()
                institute.save(update_fields=[
                    "status", "approved_by", "approved_at", "updated_at"
                ])
                # Uses get_or_create so an existing paid subscription is never replaced.
                start_free_trial(institute, created_by=request.user)
                approved += 1

        self.message_user(
            request,
            f"{approved} pending institute application(s) approved and trial access checked.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Reject selected institute applications")
    def reject_selected(self, request, queryset):
        updated = queryset.filter(status=Institute.Status.PENDING).update(
            status=Institute.Status.REJECTED, approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(request, f"{updated} pending institute application(s) rejected.", level=messages.WARNING)

    @admin.action(description="Suspend selected approved institutes")
    def suspend_selected(self, request, queryset):
        updated = queryset.filter(status=Institute.Status.APPROVED).update(status=Institute.Status.SUSPENDED)
        self.message_user(request, f"{updated} approved institute(s) suspended.", level=messages.WARNING)


@admin.register(InstituteMembership)
class InstituteMembershipAdmin(admin.ModelAdmin):
    list_display = ("institute", "user", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active", "institute")
    search_fields = ("institute__name", "user__email")
    readonly_fields = ("joined_at",)
    autocomplete_fields = ("institute", "user")


class SuperAdminOnlyModelAdmin(admin.ModelAdmin):
    def _is_super_admin(self, request):
        return (
            request.user.is_active
            and request.user.is_superuser
            and getattr(request.user, "role", None) == "SUPER_ADMIN"
        )

    def has_module_permission(self, request):
        return self._is_super_admin(request)

    def has_view_permission(self, request, obj=None):
        return self._is_super_admin(request)

    def has_add_permission(self, request):
        return self._is_super_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_super_admin(request)

    def has_delete_permission(self, request, obj=None):
        return self._is_super_admin(request)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(SuperAdminOnlyModelAdmin):
    list_display = ("name", "code", "duration_days", "price", "currency", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}


@admin.register(InstituteSubscription)
class InstituteSubscriptionAdmin(SuperAdminOnlyModelAdmin):
    list_display = ("institute", "plan", "status", "starts_at", "ends_at", "amount_paid", "effective_status")
    list_filter = ("status", "plan", "starts_at", "ends_at")
    search_fields = ("institute__name", "institute__owner__email", "payment_reference")
    autocomplete_fields = ("institute",)
    readonly_fields = ("created_at", "updated_at", "created_by")
    actions = ("activate_subscriptions", "suspend_subscriptions", "cancel_subscriptions", "renew_subscriptions")

    @admin.action(description="Activate selected subscriptions")
    def activate_subscriptions(self, request, queryset):
        updated = queryset.update(status=InstituteSubscription.Status.ACTIVE)
        self.message_user(request, f"{updated} subscription(s) activated.", level=messages.SUCCESS)

    @admin.action(description="Suspend selected subscriptions")
    def suspend_subscriptions(self, request, queryset):
        updated = queryset.update(status=InstituteSubscription.Status.SUSPENDED)
        self.message_user(request, f"{updated} subscription(s) suspended.", level=messages.WARNING)

    @admin.action(description="Cancel selected subscriptions")
    def cancel_subscriptions(self, request, queryset):
        updated = queryset.update(status=InstituteSubscription.Status.CANCELLED)
        self.message_user(request, f"{updated} subscription(s) cancelled.", level=messages.WARNING)

    @admin.action(description="Renew selected subscriptions for their plan duration")
    def renew_subscriptions(self, request, queryset):
        renewed = 0
        for subscription in queryset.select_related("plan"):
            subscription.renew()
            renewed += 1
        self.message_user(request, f"{renewed} subscription(s) renewed.", level=messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
