from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core import signing
from django.core import mail
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from institutes.models import (
    Institute,
    InstituteMembership,
    InstituteSubscription,
    SubscriptionPlan,
)

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StudentRegistrationAndEnrollmentTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "first_name": "Test",
            "last_name": "Student",
            "email": "new-student@example.test",
            "phone": "9876543210",
            "password": "A-Strong-Student-Password-2026!",
            "confirm_password": "A-Strong-Student-Password-2026!",
        }
        data.update(overrides)
        return data

    def setUp(self):
        self.owner = User.objects.create_user(
            email="registration-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.admin = User.objects.create_superuser(
            email="registration-admin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.institute = Institute.objects.create(
            name="Enrollment Academy",
            owner=self.owner,
            email="enrollment@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
            approved_by=self.admin,
        )
        # An approved institute must have an active trial or paid subscription
        # before its enrolled students can access the member dashboard.
        trial_plan = SubscriptionPlan.objects.create(
            name="Enrollment Test Trial",
            code="enrollment-test-trial",
            duration_days=7,
            price=0,
            max_students=25,
            max_staff=2,
        )
        InstituteSubscription.objects.create(
            institute=self.institute,
            plan=trial_plan,
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(days=7),
            amount_paid=0,
        )

    def test_registration_creates_inactive_student_and_sends_verification_email(self):
        response = self.client.post(
            reverse("accounts:student_register"), self.registration_data()
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/registration_pending.html")
        student = User.objects.get(email="new-student@example.test")
        self.assertEqual(student.role, User.Roles.STUDENT)
        self.assertFalse(student.is_active)
        self.assertFalse(student.is_email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your TypingSkillZone student account", mail.outbox[0].subject)

    def test_registration_rejects_duplicate_email(self):
        User.objects.create_user(
            email="new-student@example.test",
            password="Existing-Strong-Password-2026!",
        )
        response = self.client.post(
            reverse("accounts:student_register"), self.registration_data()
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.filter(email="new-student@example.test").count(), 1)

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("accounts:student_register"),
            self.registration_data(confirm_password="Different-Password-2026!"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("confirm_password", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="new-student@example.test").exists())

    def test_verification_link_get_does_not_activate_or_log_in_student(self):
        student = User.objects.create_user(
            email="verify-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_active=False,
        )
        token = signing.dumps(
            {"user_id": student.pk},
            salt="typingskillzone.student.email-verification",
        )
        response = self.client.get(
            reverse("accounts:verify_email", kwargs={"token": token})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm your email")
        student.refresh_from_db()
        self.assertFalse(student.is_active)
        self.assertFalse(student.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_verification_post_activates_student_and_logs_them_in(self):
        student = User.objects.create_user(
            email="verify-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_active=False,
        )
        token = signing.dumps(
            {"user_id": student.pk},
            salt="typingskillzone.student.email-verification",
        )
        response = self.client.post(
            reverse("accounts:verify_email", kwargs={"token": token})
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertTrue(student.is_active)
        self.assertTrue(student.is_email_verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), student.pk)

    def test_invalid_verification_token_is_rejected(self):
        response = self.client.get(
            reverse("accounts:verify_email", kwargs={"token": "invalid-token"})
        )
        self.assertEqual(response.status_code, 400)

    def test_profile_can_be_updated_but_email_cannot(self):
        student = User.objects.create_user(
            email="profile-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_email_verified=True,
        )
        self.client.force_login(student)
        response = self.client.post(
            reverse("accounts:student_profile"),
            {"first_name": "Updated", "last_name": "Learner", "phone": "9999999999"},
        )
        self.assertRedirects(response, reverse("accounts:student_profile"))
        student.refresh_from_db()
        self.assertEqual(student.first_name, "Updated")
        self.assertEqual(student.last_name, "Learner")
        self.assertEqual(student.email, "profile-student@example.test")

    def test_student_can_enroll_using_approved_institute_registration_code(self):
        student = User.objects.create_user(
            email="enroll-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_email_verified=True,
        )
        self.client.force_login(student)
        response = self.client.post(
            reverse("accounts:enroll_institute"),
            {"registration_code": self.institute.registration_code},
        )
        self.assertRedirects(response, reverse("institutes:student_dashboard"))
        membership = InstituteMembership.objects.get(institute=self.institute, user=student)
        self.assertEqual(membership.role, InstituteMembership.Role.STUDENT)
        self.assertTrue(membership.is_active)

    def test_enrollment_rejects_pending_or_suspended_institute(self):
        student = User.objects.create_user(
            email="blocked-enroll-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.institute.status = Institute.Status.SUSPENDED
        self.institute.save(update_fields=["status", "updated_at"])
        self.client.force_login(student)
        response = self.client.post(
            reverse("accounts:enroll_institute"),
            {"registration_code": self.institute.registration_code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("registration_code", response.context["form"].errors)
        self.assertFalse(InstituteMembership.objects.filter(user=student).exists())

    def test_duplicate_institute_enrollment_is_rejected(self):
        student = User.objects.create_user(
            email="duplicate-enroll-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        InstituteMembership.objects.create(
            institute=self.institute,
            user=student,
            role=InstituteMembership.Role.STUDENT,
        )
        self.client.force_login(student)
        response = self.client.post(
            reverse("accounts:enroll_institute"),
            {"registration_code": self.institute.registration_code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("registration_code", response.context["form"].errors)
        self.assertEqual(
            InstituteMembership.objects.filter(institute=self.institute, user=student).count(),
            1,
        )

    def test_non_student_cannot_use_student_profile_or_enrollment(self):
        self.client.force_login(self.owner)
        profile = self.client.get(reverse("accounts:student_profile"))
        enroll = self.client.get(reverse("accounts:enroll_institute"))
        self.assertEqual(profile.status_code, 403)
        self.assertEqual(enroll.status_code, 403)
