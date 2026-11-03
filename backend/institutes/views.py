from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import User
from .forms import InstituteRegistrationForm
from .models import Institute


def is_super_admin(user):
    return user.is_authenticated and user.is_superuser and user.role == User.Roles.SUPER_ADMIN


@login_required
@user_passes_test(is_super_admin, login_url="/admin/login/")
def super_admin_dashboard(request):
    status_counts = {
        item["status"]: item["total"]
        for item in Institute.objects.values("status").annotate(total=Count("id"))
    }
    context = {
        "total_users": User.objects.count(),
        "total_students": User.objects.filter(role=User.Roles.STUDENT).count(),
        "total_institutes": Institute.objects.count(),
        "pending_institutes": Institute.objects.filter(status=Institute.Status.PENDING).count(),
        "approved_institutes": Institute.objects.filter(status=Institute.Status.APPROVED).count(),
        "rejected_institutes": Institute.objects.filter(status=Institute.Status.REJECTED).count(),
        "suspended_institutes": Institute.objects.filter(status=Institute.Status.SUSPENDED).count(),
        "recent_institutes": Institute.objects.select_related("owner").order_by("-created_at")[:8],
        "status_counts": status_counts,
    }
    return render(request, "institutes/super_admin_dashboard.html", context)


@login_required
@user_passes_test(is_super_admin, login_url="/admin/login/")
@require_POST
def review_institute(request, pk, action):
    institute = get_object_or_404(Institute, pk=pk)

    if action == "approve" and institute.status == Institute.Status.PENDING:
        institute.status = Institute.Status.APPROVED
        institute.approved_by = request.user
        institute.approved_at = timezone.now()
        institute.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        messages.success(request, f"{institute.name} has been approved.")
    elif action == "reject" and institute.status == Institute.Status.PENDING:
        institute.status = Institute.Status.REJECTED
        institute.approved_by = request.user
        institute.approved_at = timezone.now()
        institute.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        messages.warning(request, f"{institute.name} has been rejected.")
    elif action == "suspend" and institute.status == Institute.Status.APPROVED:
        institute.status = Institute.Status.SUSPENDED
        institute.save(update_fields=["status", "updated_at"])
        messages.warning(request, f"{institute.name} has been suspended.")
    else:
        messages.error(request, "This action is not valid for the institute's current status.")

    return redirect("institutes:super_admin_dashboard")


@require_http_methods(["GET", "POST"])
def institute_register(request):
    if request.user.is_authenticated:
        messages.info(request, "Please log out before registering a new institute.")
        return redirect("admin:index")

    if request.method == "POST":
        form = InstituteRegistrationForm(request.POST)
        if form.is_valid():
            institute = form.save()
            return render(
                request,
                "institutes/registration_success.html",
                {"institute": institute},
            )
    else:
        form = InstituteRegistrationForm()

    return render(request, "institutes/register.html", {"form": form})
