from django.contrib import admin
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