"""Rate-limited password recovery for active, email-verified accounts."""
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetView
from django.http import HttpResponse

from .security import is_rate_limited

User = get_user_model()


class VerifiedPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        users = User._default_manager.filter(
            email__iexact=email,
            is_active=True,
            is_email_verified=True,
        )
        for user in users:
            if user.has_usable_password():
                yield user


class ThrottledPasswordResetView(PasswordResetView):
    form_class = VerifiedPasswordResetForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = "/accounts/password-reset/done/"

    def form_valid(self, form):
        email = form.cleaned_data.get("email", "")
        limited_email = is_rate_limited(
            "password-reset-email", self.request, identity=email, limit=3, window=3600
        )
        limited_ip = is_rate_limited(
            "password-reset-ip", self.request, limit=10, window=3600
        )
        if limited_email or limited_ip:
            return HttpResponse(
                "Too many password reset requests. Please try again later.", status=429
            )
        return super().form_valid(form)
