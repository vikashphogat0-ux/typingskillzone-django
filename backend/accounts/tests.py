from datetime import timedelta
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from exams.models import ExamConfiguration
from institutes.models import (
    Institute,
    InstituteMembership,
    InstituteSubscription,
    SubscriptionPlan,
)
from learners.models import LearnerProfile
from passages.models import PassageSource, SimulatorPassage
from typing_sessions.models import TypingSession


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
    def test_authenticated_student_visiting_registration_redirects_to_student_dashboard(self):
        student = User.objects.create_user(
            email="independent-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_email_verified=True,
    )
        self.client.force_login(student)

        response = self.client.get(reverse("accounts:student_register"))

        self.assertRedirects(
            response,
            reverse("exams:catalogue"),
            fetch_redirect_response=False,
    )

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
        student.email_verification_sent_at = timezone.now()
        student.save(update_fields=["email_verification_sent_at"])
        token = signing.dumps(
            {"user_id": student.pk, "issued_at": student.email_verification_sent_at.isoformat()},
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
        student.email_verification_sent_at = timezone.now()
        student.save(update_fields=["email_verification_sent_at"])
        token = signing.dumps(
            {"user_id": student.pk, "issued_at": student.email_verification_sent_at.isoformat()},
            salt="typingskillzone.student.email-verification",
        )
        response = self.client.post(
            reverse("accounts:verify_email", kwargs={"token": token})
        )
        self.assertRedirects(response, reverse("exams:catalogue"), fetch_redirect_response=False)
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


    def test_student_self_enrollment_rejects_expired_subscription(self):
        self.institute.subscription.ends_at = timezone.now() - timedelta(seconds=1)
        self.institute.subscription.save(update_fields=["ends_at", "updated_at"])
        student = User.objects.create_user(
            email="expired-self-enroll@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.client.force_login(student)
        response = self.client.post(
            reverse("accounts:enroll_institute"),
            {"registration_code": self.institute.registration_code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("registration_code", response.context["form"].errors)
        self.assertFalse(InstituteMembership.objects.filter(institute=self.institute, user=student).exists())

    def test_student_self_enrollment_rejects_full_student_seats(self):
        students = [
            User.objects.create_user(
                email=f"self-enroll-seat-{index}@example.test",
                password="Student-Strong-Password-2026!",
                role=User.Roles.STUDENT,
            )
            for index in range(25)
        ]
        InstituteMembership.objects.bulk_create([
            InstituteMembership(
                institute=self.institute,
                user=student,
                role=InstituteMembership.Role.STUDENT,
                is_active=True,
            )
            for student in students
        ])
        extra = User.objects.create_user(
            email="self-enroll-over-limit@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.client.force_login(extra)
        response = self.client.post(
            reverse("accounts:enroll_institute"),
            {"registration_code": self.institute.registration_code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("registration_code", response.context["form"].errors)
        self.assertFalse(InstituteMembership.objects.filter(institute=self.institute, user=extra).exists())

    def test_verification_token_cannot_be_replayed_after_success(self):
        student = User.objects.create_user(
            email="replay-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_active=False,
        )
        student.email_verification_sent_at = timezone.now()
        student.save(update_fields=["email_verification_sent_at"])
        token = signing.dumps(
            {"user_id": student.pk, "issued_at": student.email_verification_sent_at.isoformat()},
            salt="typingskillzone.student.email-verification",
        )
        first = self.client.post(reverse("accounts:verify_email", kwargs={"token": token}))
        self.assertRedirects(first, reverse("exams:catalogue"), fetch_redirect_response=False)
        replay_client = self.client_class()
        replay = replay_client.post(reverse("accounts:verify_email", kwargs={"token": token}))
        self.assertEqual(replay.status_code, 400)
        self.assertNotIn("_auth_user_id", replay_client.session)

    def test_resend_verification_sends_new_link_without_revealing_account_existence(self):
        student = User.objects.create_user(
            email="resend-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
            is_active=False,
            is_email_verified=False,
        )
        response = self.client.post(
            reverse("accounts:resend_verification"),
            {"email": student.email},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        student.refresh_from_db()
        self.assertIsNotNone(student.email_verification_sent_at)


class StudentDashboardViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="dashboard-student@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.non_student = User.objects.create_user(
            email="dashboard-admin@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.ADMIN,
        )

    def test_dashboard_requires_student_role(self):
        self.client.force_login(self.non_student)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_shows_stats_and_recent_sessions(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/student_dashboard.html")
        self.assertEqual(response.context["total_sessions"], 0)
        self.assertEqual(response.context["completed_sessions"], 0)
        self.assertEqual(response.context["avg_wpm"], 0)
        self.assertEqual(response.context["avg_accuracy"], 0)
        self.assertEqual(list(response.context["recent"]), [])
        self.assertIsInstance(response.context["profile"], LearnerProfile)

    def test_dashboard_independent_student_no_institute_required(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 200)


class StudentResultHistoryViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="history-student@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.non_student = User.objects.create_user(
            email="history-admin@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.ADMIN,
        )
        self.exam = ExamConfiguration.objects.create(
            code="TEST-EXAM",
            name="Test Exam",
            category=ExamConfiguration.Category.PRACTICE,
            duration_seconds=600,
            is_active=True,
        )
        self.source = PassageSource.objects.create(
            title="Test Passage",
            content="The quick brown fox jumps over the lazy dog.",
            language="ENGLISH",
            status=PassageSource.Status.PUBLISHED,
        )
        self.publication = SimulatorPassage.objects.create(
            exam=self.exam,
            source=self.source,
            serial_number=1,
            status=SimulatorPassage.Status.PUBLISHED,
        )

    def _create_session(self, state, scoring_version="", result_snapshot=None):
        return TypingSession.objects.create(
            learner=self.student,
            publication=self.publication,
            state=state,
            reference_text="The quick brown fox.",
            submitted_text="The quick brown fox.",
            rules_snapshot={},
            scoring_version=scoring_version,
            result_snapshot=result_snapshot or {},
        )

    def test_result_history_requires_student_role(self):
        self.client.force_login(self.non_student)
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 403)

    def test_result_history_includes_submitted_sessions(self):
        self.client.force_login(self.student)
        self._create_session(
            TypingSession.State.SUBMITTED,
            scoring_version="v1",
            result_snapshot={"net_wpm": 40.5, "accuracy_percent": 96.0},
        )
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 1)

    def test_result_history_includes_expired_with_score(self):
        self.client.force_login(self.student)
        self._create_session(
            TypingSession.State.EXPIRED,
            scoring_version="v1",
            result_snapshot={"net_wpm": 30.0, "accuracy_percent": 90.0},
        )
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 1)

    def test_result_history_excludes_expired_without_score(self):
        self.client.force_login(self.student)
        self._create_session(TypingSession.State.EXPIRED, scoring_version="")
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 0)

    def test_result_history_filters_by_language(self):
        self.client.force_login(self.student)
        self._create_session(
            TypingSession.State.SUBMITTED,
            scoring_version="v1",
            result_snapshot={"net_wpm": 40.0, "accuracy_percent": 95.0},
        )
        hindi_source = PassageSource.objects.create(
            title="Hindi Passage",
            content="हिंदी गद्यांश",
            language="HINDI",
            status=PassageSource.Status.PUBLISHED,
        )
        hindi_pub = SimulatorPassage.objects.create(
            exam=self.exam,
            source=hindi_source,
            serial_number=2,
            status=SimulatorPassage.Status.PUBLISHED,
        )
        TypingSession.objects.create(
            learner=self.student,
            publication=hindi_pub,
            state=TypingSession.State.SUBMITTED,
            reference_text="हिंदी गद्यांश",
            submitted_text="हिंदी गद्यांश",
            rules_snapshot={},
            scoring_version="v1",
            result_snapshot={"net_wpm": 25.0, "accuracy_percent": 88.0},
        )
        response = self.client.get(
            reverse("accounts:student_result_history") + "?language=HINDI"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 1)
        self.assertEqual(
            response.context["page_obj"].object_list[0].publication.source.language,
            "HINDI",
        )

    def test_result_history_filters_by_exam(self):
        self.client.force_login(self.student)
        self._create_session(
            TypingSession.State.SUBMITTED,
            scoring_version="v1",
            result_snapshot={"net_wpm": 40.0, "accuracy_percent": 95.0},
        )
        response = self.client.get(
            reverse("accounts:student_result_history") + f"?exam={self.exam.code}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 1)

    def test_result_history_date_from_cannot_be_later_than_date_to(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts:student_result_history")
            + "?date_from=2026-01-10&date_to=2026-01-01"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_date_from"])
        self.assertIsNone(response.context["selected_date_to"])

    def test_result_history_pagination(self):
        self.client.force_login(self.student)
        for i in range(25):
            self._create_session(
                TypingSession.State.SUBMITTED,
                scoring_version="v1",
                result_snapshot={"net_wpm": float(40 + i), "accuracy_percent": 95.0},
            )
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_result_history_empty_state(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:student_result_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 0)


class PassageLibraryViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="library-student@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.non_student = User.objects.create_user(
            email="library-admin@example.test",
            password="Strong-Password-2026!",
            role=User.Roles.ADMIN,
        )
        self.exam = ExamConfiguration.objects.create(
            code="LIB-EXAM",
            name="Library Exam",
            category=ExamConfiguration.Category.PRACTICE,
            duration_seconds=600,
            is_active=True,
        )
        self.source = PassageSource.objects.create(
            title="Library Passage Alpha",
            content="Alpha passage content for typing practice.",
            language="ENGLISH",
            status=PassageSource.Status.PUBLISHED,
        )
        self.publication = SimulatorPassage.objects.create(
            exam=self.exam,
            source=self.source,
            serial_number=1,
            status=SimulatorPassage.Status.PUBLISHED,
        )
        self.draft_source = PassageSource.objects.create(
            title="Draft Passage",
            content="This is a draft.",
            language="ENGLISH",
            status=PassageSource.Status.DRAFT,
        )
        SimulatorPassage.objects.create(
            exam=self.exam,
            source=self.draft_source,
            serial_number=2,
            status=SimulatorPassage.Status.PUBLISHED,
        )

    def test_passage_library_requires_student_role(self):
        self.client.force_login(self.non_student)
        response = self.client.get(reverse("accounts:passage_library"))
        self.assertEqual(response.status_code, 403)

    def test_passage_library_shows_published_passages_only(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:passage_library"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/passage_library.html")
        self.assertTrue(response.context["exam_selection"])
        self.assertContains(response, self.exam.name)
        self.assertNotIn("passages", response.context)

    def test_passage_library_filters_by_exam(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts:passage_library") + f"?exam={self.exam.code}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["passages"]), 1)

    def test_passage_library_filters_by_language(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts:passage_library") + "?exam=LIB-EXAM&language=ENGLISH"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["passages"]), 1)

    def test_passage_library_search(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts:passage_library") + "?exam=LIB-EXAM&search=Alpha"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["passages"]), 1)

    def test_passage_library_empty_state(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts:passage_library") + "?exam=LIB-EXAM&language=HINDI"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["passages"]), 0)

    def test_passage_library_links_to_simulator_detail(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:passage_library"))
        self.assertContains(
            response,
            reverse("accounts:passage_library") + f"?exam={self.exam.code}",
        )
