from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import InstituteEnrollmentForm, StudentProfileForm, StudentRegistrationForm

User = get_user_model()
VERIFICATION_SALT = "typingskillzone.student.email-verification"
VERIFICATION_MAX_AGE = 60 * 60 * 24


def student_register(request):
    if request.user.is_authenticated:
        return redirect("institutes:student_dashboard")
    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        token = signing.dumps({"user_id": user.pk}, salt=VERIFICATION_SALT)
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
        return render(request, "accounts/registration_pending.html", {"email": user.email})
    return render(request, "accounts/student_register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def verify_student_email(request, token):
    try:
        payload = signing.loads(token, salt=VERIFICATION_SALT, max_age=VERIFICATION_MAX_AGE)
        user = User.objects.get(pk=payload["user_id"], role=User.Roles.STUDENT)
    except (signing.BadSignature, signing.SignatureExpired, KeyError, ValueError, TypeError):
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "message": "This verification link is invalid or has expired. Please request a new link.",
        }, status=400)
    except User.DoesNotExist:
        return HttpResponse("Account not found.", status=404)

    if request.method == "GET":
        if user.is_email_verified and user.is_active:
            return render(request, "accounts/verification_result.html", {
                "success": True,
                "message": "Your email is already verified. You can sign in to your student account.",
                "already_verified": True,
            })
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "confirmation": True,
            "token": token,
            "message": "Confirm that you want to verify this email address and activate your student account.",
        })

    if not user.is_email_verified or not user.is_active:
        user.is_email_verified = True
        user.is_active = True
        user.save(update_fields=["is_email_verified", "is_active"])
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
        membership = form.save()
        messages.success(request, f"You are now enrolled at {membership.institute.name}.")
        return redirect("institutes:student_dashboard")
    return render(request, "accounts/enroll_institute.html", {"form": form})
