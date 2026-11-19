from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from institutes.models import Institute


class IndependentStudentLoginTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(
            email="independent@example.com", password="SafePassword123!",
            is_active=True, is_email_verified=True,
        )
        self.owner = User.objects.create_user(
            email="owner@example.com", password="SafePassword123!", role=User.Roles.INSTITUTE_OWNER,
            is_active=True, is_email_verified=True,
        )
        self.url = reverse("accounts:student_login")

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_independent_student_signs_in_to_account_dashboard(self):
        response = self.client.post(self.url, {"username": "independent@example.com", "password": "SafePassword123!"})
        self.assertRedirects(response, reverse("accounts:student_dashboard"), fetch_redirect_response=False)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(self.url, {"username": "independent@example.com", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_owner_cannot_use_student_account_login(self):
        response = self.client.post(self.url, {"username": "owner@example.com", "password": "SafePassword123!"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_external_next_url_is_ignored(self):
        response = self.client.post(
            f"{self.url}?next=https://evil.example.com/",
            {"username": "independent@example.com", "password": "SafePassword123!"},
        )
        self.assertRedirects(response, reverse("accounts:student_dashboard"), fetch_redirect_response=False)

    def test_protected_page_redirects_to_account_login(self):
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertTrue(response.url.startswith(self.url), response.url)
