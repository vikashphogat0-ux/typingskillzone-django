import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from exams.management.commands.seed_typing_rule_profiles import PROFILES
from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam

from .drafts import DRAFT_MAX_CHARS, load_draft_text
from .models import TypingSession
from .services import save_draft, start_session, submit_session


class RemediationBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.learner = User.objects.create_user(email="learner@example.com", password="SafePassword123!")
        self.other = User.objects.create_user(email="other@example.com", password="SafePassword123!")
        self.exam = ExamConfiguration.objects.create(
            code="remediation-exam", name="Remediation Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.source = PassageSource.objects.create(
            title="Remediation", content="The quick brown fox.", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(self.source, self.exam)


class LiveAttemptReuseTests(RemediationBase):
    def test_second_start_reopens_the_live_attempt(self):
        first = start_session(learner=self.learner, publication=self.publication)
        second = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TypingSession.objects.filter(learner=self.learner).count(), 1)

    def test_expired_live_attempt_is_not_reused(self):
        first = start_session(learner=self.learner, publication=self.publication)
        TypingSession.objects.filter(pk=first.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
        second = start_session(learner=self.learner, publication=self.publication)
        self.assertNotEqual(first.pk, second.pk)


class AutosaveDraftTests(RemediationBase):
    def test_draft_is_saved_loaded_and_cleared_on_submit(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        save_draft(session_id=attempt.pk, learner=self.learner, typed_text="The quick")
        self.assertEqual(load_draft_text(attempt.pk), "The quick")
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text="The quick brown fox.")
        self.assertEqual(load_draft_text(attempt.pk), "")

    def test_draft_is_refused_for_another_learner(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(TypingSession.DoesNotExist):
            save_draft(session_id=attempt.pk, learner=self.other, typed_text="x")

    def test_draft_is_refused_after_submission(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text="The quick brown fox.")
        with self.assertRaises(ValidationError):
            save_draft(session_id=attempt.pk, learner=self.learner, typed_text="again")

    def test_oversized_draft_is_refused(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(ValidationError):
            save_draft(session_id=attempt.pk, learner=self.learner, typed_text="x" * (DRAFT_MAX_CHARS + 1))

    def test_draft_endpoint_requires_login(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        response = self.client.post(reverse("typing_sessions:draft", args=[attempt.pk]), {"typed_text": "x"})
        self.assertEqual(response.status_code, 302)


class PolicyTelemetryTests(RemediationBase):
    def test_policy_events_are_recorded_but_never_change_the_score(self):
        text = "The quick brown fox."
        a = start_session(learner=self.learner, publication=self.publication)
        with_events = submit_session(session_id=a.pk, learner=self.learner, typed_text=text, client_policy_events=7)
        b = start_session(learner=self.learner, publication=self.publication)
        without = submit_session(session_id=b.pk, learner=self.learner, typed_text=text, client_policy_events=None)
        self.assertEqual(with_events.result_snapshot["client_policy_events_unverified"], 7)
        self.assertNotIn("client_policy_events_unverified", without.result_snapshot)
        self.assertEqual(with_events.result_snapshot["net_wpm"], without.result_snapshot["net_wpm"])


class SeedAndCommandTests(TestCase):
    def test_error_based_seed_profiles_count_whole_words(self):
        for name, profile in PROFILES.items():
            if profile.get("scoring_mode") in {"ERROR_PERCENTAGE", "STROKE_PENALTY"}:
                with self.subTest(exam=name):
                    self.assertTrue(profile.get("error_rules", {}).get("count_word_errors"))

    def test_reconcile_command_is_dry_run_by_default(self):
        exam = ExamConfiguration.objects.create(
            code="legacy-error-exam", name="Legacy Error Exam", language="ENGLISH", script="LATIN",
            scoring_mode="ERROR_PERCENTAGE", error_rules={},
        )
        call_command("reconcile_word_error_rules", stdout=io.StringIO())
        exam.refresh_from_db()
        self.assertFalse(exam.error_rules.get("count_word_errors"))
        call_command("reconcile_word_error_rules", "--apply", stdout=io.StringIO())
        exam.refresh_from_db()
        self.assertTrue(exam.error_rules.get("count_word_errors"))


class ResultHistoryDateTests(TestCase):
    def test_maximum_date_does_not_crash(self):
        User = get_user_model()
        student = User.objects.create_user(
            email="dates@example.com", password="SafePassword123!", is_active=True, is_email_verified=True
        )
        self.client.force_login(student)
        response = self.client.get(reverse("accounts:student_result_history"), {"date_to": "9999-12-31"})
        self.assertEqual(response.status_code, 200)
