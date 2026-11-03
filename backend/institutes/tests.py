from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Institute

User = get_user_model()


class SuperAdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="superadmin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.owner = User.objects.create_user(
            email="owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.institute = Institute.objects.create(
            name="Dashboard Test Academy",
            owner=self.owner,
            email="academy@example.test",
            phone="9876543210",
            city="Panipat",
            state="Haryana",
        )

    def test_super_admin_can_open_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("institutes:super_admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard Test Academy")
        self.assertEqual(response.context["pending_institutes"], 1)

    def test_non_super_admin_cannot_open_dashboard(self):
        student = User.objects.create_user(
            email="student@example.test",
            password="Student-Strong-Password-2026!",
        )
        self.client.force_login(student)
        response = self.client.get(reverse("institutes:super_admin_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_approve_pending_institute(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse(
                "institutes:review_institute",
                args=[self.institute.pk, "approve"],
            )
        )
        self.assertRedirects(response, reverse("institutes:super_admin_dashboard"))
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.APPROVED)
        self.assertEqual(self.institute.approved_by, self.admin)
        self.assertIsNotNone(self.institute.approved_at)

    def test_approval_action_rejects_get_requests(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse(
                "institutes:review_institute",
                args=[self.institute.pk, "approve"],
            )
        )
        self.assertEqual(response.status_code, 405)
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.PENDING)
