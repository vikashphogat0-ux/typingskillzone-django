import logging
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import User
from accounts.security import is_rate_limited
from .forms import InstituteAdminEditForm, InstituteMemberAddForm, InstituteRegistrationForm
from .models import Institute, InstituteMembership, InstituteSubscription, SubscriptionPlan
from .owner_verification import send_owner_verification_email


logger = logging.getLogger(__name__)

TRIAL_PLAN_CODE = "free-trial"
TRIAL_STUDENT_LIMIT = 25
TRIAL_STAFF_LIMIT = 2
TRIAL_DURATION_DAYS = 7


def get_free_trial_plan():
    plan, _ = SubscriptionPlan.objects.get_or_create(
        code=TRIAL_PLAN_CODE,
        defaults={
            "name": "7-Day Free Trial",
            "description": "Seven-day institute trial with 25 student seats and 2 staff seats.",
            "duration_days": TRIAL_DURATION_DAYS,
            "price": 0,
            "currency": "INR",
            "max_students": TRIAL_STUDENT_LIMIT,
            "max_staff": TRIAL_STAFF_LIMIT,
            "is_active": True,
        },
    )
    return plan


def start_free_trial(institute, *, created_by=None):
    if institute.status != Institute.Status.APPROVED:
        return None
    plan = get_free_trial_plan()
    now = timezone.now()
    subscription, _ = InstituteSubscription.objects.get_or_create(
        institute=institute,
        defaults={
            "plan": plan,
            "status": InstituteSubscription.Status.ACTIVE,
            "starts_at": now,
            "ends_at": now + timedelta(days=TRIAL_DURATION_DAYS),
            "amount_paid": 0,
            "created_by": created_by,
        },
    )
    return subscription


def active_subscription_for(institute):
    try:
        subscription = institute.subscription
    except InstituteSubscription.DoesNotExist:
        return None
    return subscription if subscription.is_currently_active else None


def subscription_limit_reached(institute, role):
    subscription = active_subscription_for(institute)
    if subscription is None:
        return True
    limit = (
        subscription.plan.max_students
        if role == InstituteMembership.Role.STUDENT
        else subscription.plan.max_staff
    )
    if limit is None:
        return False
    current = InstituteMembership.objects.filter(
        institute=institute, role=role, is_active=True
    ).count()
    return current >= limit



def create_membership_within_limits(institute, form, role):
    """Recheck subscription and seat capacity inside the membership write transaction."""
    with transaction.atomic():
        locked_institute = Institute.objects.select_for_update().get(pk=institute.pk)
        if locked_institute.status != Institute.Status.APPROVED:
            raise ValidationError("This institute is not approved.")
        subscription = active_subscription_for(locked_institute)
        if subscription is None:
            raise ValidationError("This institute's trial or subscription has expired.")
        limit = (
            subscription.plan.max_students
            if role == InstituteMembership.Role.STUDENT
            else subscription.plan.max_staff
        )
        if limit is not None and InstituteMembership.objects.filter(
            institute=locked_institute, role=role, is_active=True
        ).count() >= limit:
            raise ValidationError("The seat limit for this membership type has been reached.")
        return form.save()


def member_login_required(view):
    """Send anonymous visitors to the login page for the requested portal (student or staff)."""

    @wraps(view)
    def wrapper(request, portal, *args, **kwargs):
        if not request.user.is_authenticated:
            name = "staff_login" if portal == "staff" else "student_login"
            return redirect(f"{reverse('institutes:' + name)}?{urlencode({'next': request.get_full_path()})}")
        return view(request, portal, *args, **kwargs)

    return wrapper


def _subscription_message(institute, prefix):
    subscription = active_subscription_for(institute)
    if subscription is None:
        return (f"{prefix} No active trial or subscription exists, so members cannot "
                "access the portal until a subscription is renewed.")
    return f"{prefix} Subscription is active until {subscription.ends_at:%d %b %Y}."


def is_super_admin(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
        and user.role == User.Roles.SUPER_ADMIN
    )


def is_institute_owner(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_email_verified
        and user.role == User.Roles.INSTITUTE_OWNER
    )


def owner_login(request):
    if request.user.is_authenticated:
        if is_institute_owner(request.user):
            return redirect("institutes:owner_dashboard")
        if is_super_admin(request.user):
            return redirect("institutes:super_admin_dashboard")
        return HttpResponseForbidden("This login portal is for institute owners.")

    if request.method == "POST" and is_rate_limited("owner-login", request, identity=request.POST.get("username", ""), limit=8, window=900):
        return HttpResponseForbidden("Too many login attempts. Please try again later.")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role != User.Roles.INSTITUTE_OWNER:
            form.add_error(None, "This login portal is only for institute owner accounts.")
        elif not user.is_email_verified:
            form.add_error(None, "Please verify your email address before signing in.")
        else:
            login(request, user)
            return redirect("institutes:owner_dashboard")
    return render(request, "institutes/owner_login.html", {"form": form})


@login_required(login_url="/institutes/owner/login/")
def owner_dashboard(request):
    if not is_institute_owner(request.user):
        return HttpResponseForbidden("Institute owner access required.")

    institutes = Institute.objects.filter(owner=request.user)
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
            "subscription": InstituteSubscription.objects.filter(institute=institute).select_related("plan").first(),
        })
    return render(
        request,
        "institutes/owner_dashboard.html",
        {"institute_rows": institute_rows},
    )


@login_required(login_url="/institutes/owner/login/")
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


@login_required(login_url="/institutes/owner/login/")
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


@login_required(login_url="/institutes/owner/login/")
@require_http_methods(["GET", "POST"])
def owner_member_add(request, institute_id):
    institute = get_owner_institute(request, institute_id)
    if institute is None:
        return HttpResponseForbidden("Institute owner access required.")
    form = InstituteMemberAddForm(request.POST or None, institute=institute)
    if request.method == "POST" and form.is_valid():
        requested_role = (
            InstituteMembership.Role.STUDENT
            if form.cleaned_data["role"] == User.Roles.STUDENT
            else InstituteMembership.Role.STAFF
        )
        try:
            membership = create_membership_within_limits(institute, form, requested_role)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"{membership.user.email} was added to {institute.name}.")
            return redirect("institutes:owner_member_list", institute_id=institute.pk)
    return render(request, "institutes/owner_member_add.html", {
        "institute": institute,
        "form": form,
    })


@login_required(login_url="/institutes/owner/login/")
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
        membership.save(update_fields=["is_active"])
    elif action == "activate":
        try:
            with transaction.atomic():
                locked_institute = Institute.objects.select_for_update().get(pk=institute.pk)
                locked_membership = InstituteMembership.objects.select_for_update().get(
                    pk=membership.pk, institute=locked_institute
                )
                if active_subscription_for(locked_institute) is None:
                    raise ValidationError("This institute's trial or subscription has expired.")
                if not locked_membership.is_active and subscription_limit_reached(
                    locked_institute, locked_membership.role
                ):
                    raise ValidationError("The seat limit for this membership type has been reached.")
                locked_membership.is_active = True
                locked_membership.save(update_fields=["is_active"])
        except ValidationError as error:
            messages.error(request, error)
            return redirect("institutes:owner_member_list", institute_id=institute.pk)
    else:
        return HttpResponseForbidden("Unsupported membership action.")
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

    if request.method == "POST" and is_rate_limited(f"{portal}-login", request, identity=request.POST.get("username", ""), limit=8, window=900):
        return HttpResponseForbidden("Too many login attempts. Please try again later.")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role != required_role or not user.is_active:
            form.add_error(None, "The email or password is incorrect for this portal.")
        else:
            login(request, user)
            return redirect(_member_dashboard_name(portal))
    return render(request, f"institutes/{portal}_login.html", {"form": form, "portal": portal})


@member_login_required
def member_dashboard(request, portal):
    if portal not in {"student", "staff"}:
        return HttpResponseForbidden("Unsupported member portal.")
    required_role = _member_role_for_portal(portal)
    if not request.user.is_active or request.user.role != required_role:
        return HttpResponseForbidden("Member access required.")

    now = timezone.now()
    memberships = InstituteMembership.objects.filter(
        user=request.user,
        is_active=True,
        institute__status=Institute.Status.APPROVED,
        institute__subscription__status=InstituteSubscription.Status.ACTIVE,
        institute__subscription__starts_at__lte=now,
        institute__subscription__ends_at__gt=now,
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


@member_login_required
@require_POST
def member_logout(request, portal):
    if portal not in {"student", "staff"}:
        return HttpResponseForbidden("Unsupported member portal.")
    required_role = _member_role_for_portal(portal)
    if request.user.role != required_role:
        return HttpResponseForbidden("Member access required.")
    logout(request)
    return redirect(f"institutes:{portal}_login")


@login_required(login_url="/admin/login/")
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


@login_required(login_url="/admin/login/")
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


@login_required(login_url="/admin/login/")
@user_passes_test(is_super_admin, login_url="/admin/login/")
def institute_detail(request, pk):
    institute = get_object_or_404(
        Institute.objects.select_related("owner", "approved_by").prefetch_related("memberships__user"),
        pk=pk,
    )
    return render(request, "institutes/institute_detail.html", {"institute": institute})


@login_required(login_url="/admin/login/")
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


@login_required(login_url="/admin/login/")
@user_passes_test(is_super_admin, login_url="/admin/login/")
@require_POST
def review_institute(request, pk, action):
    institute = get_object_or_404(Institute, pk=pk)
    if action == "approve" and institute.status == Institute.Status.PENDING:
        institute.status = Institute.Status.APPROVED
        institute.approved_by = request.user
        institute.approved_at = timezone.now()
        institute.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        start_free_trial(institute, created_by=request.user)
        messages.success(request, _subscription_message(institute, f"{institute.name} has been approved."))
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
        start_free_trial(institute, created_by=request.user)
        messages.success(request, _subscription_message(institute, f"{institute.name} has been reactivated."))
    else:
        messages.error(request, "This action is not valid for the institute's current status.")
    return redirect("institutes:institute_detail", pk=institute.pk)


@require_http_methods(["GET", "POST"])
def institute_register(request):
    if request.user.is_authenticated:
        messages.info(request, "Please log out before registering a new institute.")
        return redirect("admin:index")
    if request.method == "POST" and is_rate_limited("institute-register", request, limit=5, window=3600):
        return HttpResponseForbidden("Too many registration attempts. Please try again later.")
    if request.method == "POST":
        form = InstituteRegistrationForm(request.POST)
        if form.is_valid():
            try:
                institute = form.save()
            except IntegrityError:
                form.add_error("owner_email", "An account with this email already exists.")
                return render(request, "institutes/register.html", {"form": form})
            try:
                send_owner_verification_email(request, institute.owner)
            except Exception:
                logger.exception("Unable to send owner verification email for user %s", institute.owner_id)
                messages.warning(request, "Registration was saved, but the verification email could not be sent. Use the resend option below.")
            return render(request, "institutes/registration_success.html", {"institute": institute})
    else:
        form = InstituteRegistrationForm()
    return render(request, "institutes/register.html", {"form": form})
