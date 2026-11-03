from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import User
from .forms import InstituteAdminEditForm, InstituteMemberAddForm, InstituteRegistrationForm
from .models import Institute, InstituteMembership


def is_super_admin(user):
    return user.is_authenticated and user.is_superuser and user.role == User.Roles.SUPER_ADMIN


def is_institute_owner(user):
    return user.is_authenticated and user.is_active and user.role == User.Roles.INSTITUTE_OWNER


def owner_login(request):
    if request.user.is_authenticated:
        if is_institute_owner(request.user):
            return redirect("institutes:owner_dashboard")
        if is_super_admin(request.user):
            return redirect("institutes:super_admin_dashboard")
        return HttpResponseForbidden("This login portal is for institute owners.")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role != User.Roles.INSTITUTE_OWNER:
            form.add_error(None, "This login portal is only for institute owner accounts.")
        else:
            login(request, user)
            return redirect("institutes:owner_dashboard")
    return render(request, "institutes/owner_login.html", {"form": form})


@login_required
def owner_dashboard(request):
    if not is_institute_owner(request.user):
        return HttpResponseForbidden("Institute owner access required.")

    institutes = Institute.objects.filter(owner=request.user).prefetch_related("memberships")
    approved_institutes = institutes.filter(status=Institute.Status.APPROVED)
    if not approved_institutes.exists():
        statuses = list(institutes.values_list("status", flat=True))
        if not statuses:
            access_status = "NO_INSTITUTE"
        elif Institute.Status.SUSPENDED in statuses:
            access_status = "SUSPENDED"
        elif Institute.Status.REJECTED in statuses:
            access_status = "REJECTED"
        else:
            access_status = "PENDING"
        return render(
            request,
            "institutes/owner_access_status.html",
            {"access_status": access_status},
            status=403,
        )

    institute_rows = []
    for institute in approved_institutes:
        institute_rows.append({
            "institute": institute,
            "staff_count": InstituteMembership.objects.filter(
                institute=institute, role=InstituteMembership.Role.STAFF, is_active=True
            ).count(),
            "student_count": InstituteMembership.objects.filter(
                institute=institute, role=InstituteMembership.Role.STUDENT, is_active=True
            ).count(),
        })
    return render(
        request,
        "institutes/owner_dashboard.html",
        {"institute_rows": institute_rows},
    )


@login_required
def owner_logout(request):
    if request.method != "POST":
        return HttpResponseForbidden("Logout must use POST.")
    if not is_institute_owner(request.user):
        return HttpResponseForbidden("Institute owner access required.")
    logout(request)
    return redirect("institutes:owner_login")


def get_owner_institute(request, institute_id):
    if not is_institute_owner(request.user):
        return None
    return get_object_or_404(
        Institute,
        pk=institute_id,
        owner=request.user,
        status=Institute.Status.APPROVED,
    )


@login_required
def owner_member_list(request, institute_id):
    institute = get_owner_institute(request, institute_id)
    if institute is None:
        return HttpResponseForbidden("Institute owner access required.")
    memberships = InstituteMembership.objects.filter(
        institute=institute
    ).select_related("user").order_by("role", "user__email")
    selected_role = request.GET.get("role", "")
    if selected_role in {InstituteMembership.Role.STAFF, InstituteMembership.Role.STUDENT}:
        memberships = memberships.filter(role=selected_role)
    return render(request, "institutes/owner_member_list.html", {
        "institute": institute,
        "memberships": memberships,
        "selected_role": selected_role,
        "role_choices": InstituteMembership.Role.choices,
    })


@login_required
@require_http_methods(["GET", "POST"])
def owner_member_add(request, institute_id):
    institute = get_owner_institute(request, institute_id)
    if institute is None:
        return HttpResponseForbidden("Institute owner access required.")
    form = InstituteMemberAddForm(request.POST or None, institute=institute)
    if request.method == "POST" and form.is_valid():
        membership = form.save()
        messages.success(request, f"{membership.user.email} was added to {institute.name}.")
        return redirect("institutes:owner_member_list", institute_id=institute.pk)
    return render(request, "institutes/owner_member_add.html", {
        "institute": institute,
        "form": form,
    })


@login_required
@require_POST
def owner_member_status(request, institute_id, membership_id, action):
    institute = get_owner_institute(request, institute_id)
    if institute is None:
        return HttpResponseForbidden("Institute owner access required.")
    membership = get_object_or_404(
        InstituteMembership,
        pk=membership_id,
        institute=institute,
    )
    if action == "deactivate":
        membership.is_active = False
    elif action == "activate":
        membership.is_active = True
    else:
        return HttpResponseForbidden("Unsupported membership action.")
    membership.save(update_fields=["is_active"])
    messages.success(request, f"{membership.user.email} membership status updated.")
    return redirect("institutes:owner_member_list", institute_id=institute.pk)



def _member_role_for_portal(portal):
    return User.Roles.STUDENT if portal == "student" else User.Roles.INSTITUTE_STAFF


def _member_dashboard_name(portal):
    return f"institutes:{portal}_dashboard"


def member_login(request, portal):
    if portal not in {"student", "staff"}:
        return HttpResponseForbidden("Unsupported member portal.")
    required_role = _member_role_for_portal(portal)
    if request.user.is_authenticated:
        if request.user.role == required_role:
            return redirect(_member_dashboard_name(portal))
        return HttpResponseForbidden("This account cannot use this portal.")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role != required_role or not user.is_active:
            form.add_error(None, "The email or password is incorrect for this portal.")
        else:
            login(request, user)
            return redirect(_member_dashboard_name(portal))
    return render(request, f"institutes/{portal}_login.html", {"form": form, "portal": portal})


@login_required
def member_dashboard(request, portal):
    if portal not in {"student", "staff"}:
        return HttpResponseForbidden("Unsupported member portal.")
    required_role = _member_role_for_portal(portal)
    if not request.user.is_active or request.user.role != required_role:
        return HttpResponseForbidden("Member access required.")

    memberships = InstituteMembership.objects.filter(
        user=request.user,
        is_active=True,
        institute__status=Institute.Status.APPROVED,
    ).select_related("institute").order_by("institute__name")
    if not memberships.exists():
        return render(
            request,
            "institutes/member_access_status.html",
            {"portal": portal},
            status=403,
        )
    return render(request, f"institutes/{portal}_dashboard.html", {
        "memberships": memberships,
        "portal": portal,
    })


@login_required
@require_POST
def member_logout(request, portal):
    if portal not in {"student", "staff"}:
        return HttpResponseForbidden("Unsupported member portal.")
    required_role = _member_role_for_portal(portal)
    if request.user.role != required_role:
        return HttpResponseForbidden("Member access required.")
    logout(request)
    return redirect(f"institutes:{portal}_login")


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
def institute_list(request):
    institutes = Institute.objects.select_related("owner", "approved_by")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        institutes = institutes.filter(
            Q(name__icontains=query) |
            Q(registration_code__icontains=query) |
            Q(owner__email__icontains=query) |
            Q(email__icontains=query) |
            Q(city__icontains=query)
        )
    valid_statuses = {choice[0] for choice in Institute.Status.choices}
    if status in valid_statuses:
        institutes = institutes.filter(status=status)
    return render(request, "institutes/institute_list.html", {
        "institutes": institutes,
        "query": query,
        "selected_status": status,
        "status_choices": Institute.Status.choices,
    })


@login_required
@user_passes_test(is_super_admin, login_url="/admin/login/")
def institute_detail(request, pk):
    institute = get_object_or_404(
        Institute.objects.select_related("owner", "approved_by").prefetch_related("memberships__user"),
        pk=pk,
    )
    return render(request, "institutes/institute_detail.html", {"institute": institute})


@login_required
@user_passes_test(is_super_admin, login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def institute_edit(request, pk):
    institute = get_object_or_404(Institute, pk=pk)
    form = InstituteAdminEditForm(request.POST or None, instance=institute)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{institute.name} details have been updated.")
        return redirect("institutes:institute_detail", pk=institute.pk)
    return render(request, "institutes/institute_edit.html", {"form": form, "institute": institute})


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
    elif action == "reactivate" and institute.status == Institute.Status.SUSPENDED:
        institute.status = Institute.Status.APPROVED
        institute.approved_by = request.user
        institute.approved_at = timezone.now()
        institute.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        messages.success(request, f"{institute.name} has been reactivated.")
    else:
        messages.error(request, "This action is not valid for the institute's current status.")
    return redirect("institutes:institute_detail", pk=institute.pk)


@require_http_methods(["GET", "POST"])
def institute_register(request):
    if request.user.is_authenticated:
        messages.info(request, "Please log out before registering a new institute.")
        return redirect("admin:index")
    if request.method == "POST":
        form = InstituteRegistrationForm(request.POST)
        if form.is_valid():
            institute = form.save()
            return render(request, "institutes/registration_success.html", {"institute": institute})
    else:
        form = InstituteRegistrationForm()
    return render(request, "institutes/register.html", {"form": form})
