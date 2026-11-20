
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .admin_permissions import SuperAdminOnlyAdminMixin
from .models import User


@admin.register(User)
class CustomUserAdmin(SuperAdminOnlyAdminMixin, UserAdmin):
    ordering = ('email',)

    list_display = (
        'email',
        'role',
        'is_active',
        'is_staff',
        'is_email_verified',
    )

    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'phone')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Permissions', {
            'fields': (
                'role',
                'is_active',
                'is_staff',
                'is_superuser',
                'is_email_verified',
                'groups',
                'user_permissions',
            )
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )


# --- TypingSkillZone admin overview -------------------------------------------------
# Adds live counts to the Django admin home page. Read-only queries; no permission changes.
from django.contrib import admin as _admin
from django.urls import NoReverseMatch, reverse as _reverse
from django.utils import timezone as _timezone


def _admin_url(name, query=""):
    try:
        return _reverse(name) + query
    except NoReverseMatch:
        return "#"


def tsz_admin_stats():
    from exams.models import ExamConfiguration
    from institutes.models import Institute
    from passages.models import SimulatorPassage
    from typing_sessions.models import TypingSession

    return [
        {"label": "Students", "value": User.objects.filter(role="STUDENT").count(),
         "note": "Registered student accounts", "url": _admin_url("admin:accounts_user_changelist", "?role__exact=STUDENT")},
        {"label": "Pending institutes", "value": Institute.objects.filter(status="PENDING").count(),
         "note": "Awaiting review", "url": _admin_url("admin:institutes_institute_changelist", "?status__exact=PENDING")},
        {"label": "Approved institutes", "value": Institute.objects.filter(status="APPROVED").count(),
         "note": "Active institutes", "url": _admin_url("admin:institutes_institute_changelist", "?status__exact=APPROVED")},
        {"label": "Active exams", "value": ExamConfiguration.objects.filter(is_active=True).count(),
         "note": "Exams shown in the catalogue", "url": _admin_url("admin:exams_examconfiguration_changelist")},
        {"label": "Published passages", "value": SimulatorPassage.objects.filter(status=SimulatorPassage.Status.PUBLISHED).count(),
         "note": "Available for practice", "url": _admin_url("admin:passages_simulatorpassage_changelist")},
        {"label": "Tests today", "value": TypingSession.objects.filter(started_at__date=_timezone.localdate()).count(),
         "note": "Attempts started today", "url": _admin_url("admin:typing_sessions_typingsession_changelist")},
    ]


_original_admin_index = _admin.site.index


def _tsz_index(request, extra_context=None):
    context = dict(extra_context or {})
    context["tsz_stats"] = tsz_admin_stats()
    return _original_admin_index(request, context)


_admin.site.index = _tsz_index
_admin.site.site_header = "TypingSkillZone Administration"
_admin.site.site_title = "TypingSkillZone Admin"
_admin.site.index_title = "Overview"
