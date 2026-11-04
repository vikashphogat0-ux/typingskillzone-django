import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import InstituteEnrollmentForm, StudentProfileForm, StudentRegistrationForm
from .security import is_rate_limited

User = get_user_model()
logger = logging.getLogger(__name__)
VERIFICATION_SALT = "typingskillzone.student.email-verification"
VERIFICATION_MAX_AGE = 60 * 60 * 24


def send_student_verification_email(request, user):
    issued_at = timezone.now()
    user.email_verification_sent_at = issued_at
    user.save(update_fields=["email_verification_sent_at"])
    token = signing.dumps(
        {"user_id": user.pk, "issued_at": issued_at.isoformat()},
        salt=VERIFICATION_SALT,
    )
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"token": token})
    )
    send_mail(
        "Verify your TypingSkillZone student account",
        f"Hello {user.first_name},\n\nVerify your email within 24 hours using this link:\n{verify_url}\n\nIf you did not create this account, ignore this email.",
        None,
        [user.email],
        fail_silently=False,
    )


def student_register(request):
    if request.user.is_authenticated:
        return redirect("institutes:student_dashboard")
    if request.method == "POST" and is_rate_limited("student-register", request, limit=5, window=3600):
        return HttpResponse("Too many registration attempts. Please try again later.", status=429)
    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        try:
            send_student_verification_email(request, user)
        except Exception:
            logger.exception("Unable to send student verification email for user %s", user.pk)
            messages.warning(
                request,
                "Your account was created but the verification email could not be sent. Use the resend verification option.",
            )
        return render(request, "accounts/registration_pending.html", {"email": user.email})
    return render(request, "accounts/student_register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def resend_student_verification(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if is_rate_limited("student-resend", request, identity=email, limit=3, window=3600):
            return HttpResponse("Too many requests. Please try again later.", status=429)
        if not is_rate_limited("student-resend-ip", request, limit=10, window=3600):
            user = User.objects.filter(
                email__iexact=email,
                role=User.Roles.STUDENT,
                is_active=False,
                is_email_verified=False,
            ).first()
            if user:
                try:
                    send_student_verification_email(request, user)
                except Exception:
                    logger.exception("Unable to resend student verification email for user %s", user.pk)
    # Do not reveal whether an email address belongs to an account.
    return render(request, "accounts/registration_pending.html", {
        "generic_resend_message": "If an unverified student account exists for that email, a new verification link has been sent."
    })


@require_http_methods(["GET", "POST"])
def verify_student_email(request, token):
    # Do not throttle GET previews: email security scanners may open links automatically.
    if request.method == "POST" and is_rate_limited("student-verify", request, limit=10, window=900):
        return HttpResponse("Too many verification attempts. Please try again later.", status=429)
    try:
        payload = signing.loads(token, salt=VERIFICATION_SALT, max_age=VERIFICATION_MAX_AGE)
        user = User.objects.get(pk=payload["user_id"], role=User.Roles.STUDENT)
        issued_at = payload["issued_at"]
        if not user.email_verification_sent_at or issued_at != user.email_verification_sent_at.isoformat():
            raise signing.BadSignature("Verification link has been superseded.")
    except (signing.BadSignature, signing.SignatureExpired, KeyError, ValueError, TypeError):
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "message": "This verification link is invalid, has been used, or has expired. Please request a new link.",
        }, status=400)
    except User.DoesNotExist:
        return HttpResponse("Account not found.", status=404)

    if user.is_email_verified and user.is_active:
        return render(request, "accounts/verification_result.html", {
            "success": True,
            "message": "Your email is already verified. You can sign in to your student account.",
            "already_verified": True,
        })

    if request.method == "GET":
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "confirmation": True,
            "token": token,
            "message": "Confirm that you want to verify this email address and activate your student account.",
        })

    user.is_email_verified = True
    user.is_active = True
    user.email_verification_sent_at = None
    user.save(update_fields=["is_email_verified", "is_active", "email_verification_sent_at"])
    login(request, user)
    return render(request, "accounts/verification_result.html", {
        "success": True,
        "message": "Your email is verified. Your student account is now active.",
    })


@login_required
@require_http_methods(["GET", "POST"])
def student_profile(request):
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)
    form = StudentProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:student_profile")
    return render(request, "accounts/student_profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def enroll_institute(request):
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)
    form = InstituteEnrollmentForm(request.POST or None, student=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            membership = form.save()
        except ValidationError as error:
            form.add_error("registration_code", error)
        else:
            messages.success(request, f"You are now enrolled at {membership.institute.name}.")
            return redirect("institutes:student_dashboard")
    return render(request, "accounts/enroll_institute.html", {"form": form})
