from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.cache import cache

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_verified_active_account_can_reset_password(self):
        user = User.objects.create_user(
            email="reset-verified@example.test",
            password="Old-Strong-Password-2026!",
            is_active=True,
            is_email_verified=True,
        )
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": user.email,
        })
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if "/accounts/password-reset/confirm/" in line
        )
        path = "/" + reset_url.split("/", 3)[3]
        # Django's built-in reset view consumes the emailed token on the first
        # GET, then redirects to a token-safe URL before rendering the form.
        confirm = self.client.get(path, follow=True)
        self.assertEqual(confirm.status_code, 200)
        safe_path = confirm.request["PATH_INFO"]
        response = self.client.post(safe_path, {
            "new_password1": "New-Strong-Password-2026!",
            "new_password2": "New-Strong-Password-2026!",
        })
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("New-Strong-Password-2026!"))

    def test_unverified_account_does_not_receive_reset_email(self):
        user = User.objects.create_user(
            email="reset-unverified@example.test",
            password="Old-Strong-Password-2026!",
            is_active=True,
            is_email_verified=False,
        )
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": user.email,
        })
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_requests_are_rate_limited(self):
        for attempt in range(3):
            response = self.client.post(reverse("accounts:password_reset"), {
                "email": "not-present@example.test",
            })
            self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": "not-present@example.test",
        })
        self.assertEqual(response.status_code, 429)
