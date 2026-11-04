from django.contrib.auth import get_user_model

User = get_user_model()


def is_platform_super_admin(request):
    user = request.user
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
        and user.role == User.Roles.SUPER_ADMIN
    )


class SuperAdminOnlyAdminMixin:
    """Restrict Django Admin model and inline operations to platform Super Admins."""

    def has_module_permission(self, request):
        return is_platform_super_admin(request)

    def has_view_permission(self, request, obj=None):
        return is_platform_super_admin(request)

    def has_add_permission(self, request, obj=None):
        return is_platform_super_admin(request)

    def has_change_permission(self, request, obj=None):
        return is_platform_super_admin(request)

    def has_delete_permission(self, request, obj=None):
        return is_platform_super_admin(request)
