import logging

from django.contrib import messages
from django.core import signing
from django.core.mail import send_mail
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import User
from accounts.security import is_rate_limited, is_rate_limit_suppressed

logger = logging.getLogger(__name__)
SALT = "typingskillzone.institute-owner.email-verification"
MAX_AGE = 60 * 60 * 24


def send_owner_verification_email(request, user):
    issued_at = timezone.now()
    user.email_verification_sent_at = issued_at
    user.save(update_fields=["email_verification_sent_at"])
    token = signing.dumps({"user_id": user.pk, "issued_at": issued_at.isoformat()}, salt=SALT)
    url = request.build_absolute_uri(reverse("institutes:verify_owner_email", kwargs={"token": token}))
    send_mail(
        "Verify your TypingSkillZone institute owner account",
        f"Hello {user.first_name},\n\nVerify your email within 24 hours:\n{url}\n\nIf you did not register, ignore this email.",
        None, [user.email], fail_silently=False,
    )


@require_http_methods(["GET", "POST"])
def verify_owner_email(request, token):
    if request.method == "POST" and is_rate_limited("owner-verify", request, limit=10, window=900):
        return HttpResponseForbidden("Too many verification attempts. Please try again later.")
    try:
        payload = signing.loads(token, salt=SALT, max_age=MAX_AGE)
        user = User.objects.get(pk=payload["user_id"], role=User.Roles.INSTITUTE_OWNER)
        if not user.email_verification_sent_at or payload["issued_at"] != user.email_verification_sent_at.isoformat():
            raise signing.BadSignature("Superseded verification link")
    except (signing.BadSignature, signing.SignatureExpired, KeyError, ValueError, TypeError):
        return render(request, "institutes/owner_verification_result.html", {"success": False, "message": "This link is invalid, has been used, or has expired. Request a new link."}, status=400)
    except User.DoesNotExist:
        return HttpResponseForbidden("Account not found.")
    if user.is_active and user.is_email_verified:
        return render(request, "institutes/owner_verification_result.html", {"success": True, "message": "Your email is already verified. You can sign in."})
    if request.method == "GET":
        return render(request, "institutes/owner_verification_result.html", {"confirmation": True, "token": token, "message": "Confirm your email address to activate your institute owner account."})
    user.is_active = True
    user.is_email_verified = True
    user.email_verification_sent_at = None
    user.save(update_fields=["is_active", "is_email_verified", "email_verification_sent_at"])
    return render(request, "institutes/owner_verification_result.html", {"success": True, "message": "Your email is verified. Your institute registration is awaiting Super Admin approval."})


@require_http_methods(["GET", "POST"])
def resend_owner_verification(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if is_rate_limited("owner-resend", request, identity=email, limit=3, window=3600):
            return HttpResponseForbidden("Too many requests. Please try again later.")
        if not is_rate_limited("owner-resend-ip", request, limit=10, window=3600) and not is_rate_limit_suppressed(request, "owner-resend-ip"):
            user = User.objects.filter(email__iexact=email, role=User.Roles.INSTITUTE_OWNER, is_active=False, is_email_verified=False).first()
            if user:
                try:
                    send_owner_verification_email(request, user)
                except Exception:
                    logger.exception("Unable to resend owner verification email for user %s", user.pk)
    return render(request, "institutes/owner_resend_result.html", {"message": "If an unverified institute owner account exists for that email, a new verification link has been sent."})
