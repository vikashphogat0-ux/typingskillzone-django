from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class DashboardRoutingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(email="route-student@example.com", password="SafePassword123!", is_active=True, is_email_verified=True)
        self.owner = User.objects.create_user(email="route-owner@example.com", password="SafePassword123!", role=User.Roles.INSTITUTE_OWNER, is_active=True, is_email_verified=True)
        self.admin = User.objects.create_superuser(email="route-admin@example.com", password="AdminStrong123!")

    def test_student_registration_page_sends_student_to_own_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:student_register"))
        self.assertRedirects(response, reverse("accounts:student_dashboard"), fetch_redirect_response=False)

    def test_owner_is_sent_to_owner_dashboard_not_student_portal(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("accounts:student_register"))
        self.assertRedirects(response, reverse("institutes:owner_dashboard"), fetch_redirect_response=False)

    def test_superadmin_is_sent_to_super_admin_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:student_register"))
        self.assertRedirects(response, reverse("institutes:super_admin_dashboard"), fetch_redirect_response=False)

    def test_student_login_page_links_registration(self):
        response = self.client.get(reverse("accounts:student_login"))
        self.assertContains(response, reverse("accounts:student_register"))

    def test_student_owner_and_superadmin_share_dashboard_shell(self):
        dashboard_cases = [
            (self.student, reverse("accounts:student_dashboard")),
            (self.owner, reverse("institutes:owner_dashboard")),
            (self.admin, reverse("institutes:super_admin_dashboard")),
        ]
        for user, url in dashboard_cases:
            with self.subTest(role=user.role, url=url):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="dashboard-shell"')
                self.assertContains(response, 'class="dashboard-sidebar"')
                self.assertContains(response, 'class="dashboard-topbar"')
