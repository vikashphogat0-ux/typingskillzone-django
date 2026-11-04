from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam

from .models import TypingSession
from .services import expire_session, start_session, submit_session


class TypingSessionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.learner = User.objects.create_user(email="personal@example.com", password="SafePassword123!")
        self.other = User.objects.create_user(email="institute@example.com", password="SafePassword123!")
        self.exam = ExamConfiguration.objects.create(
            code="sample-exam", name="Sample Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.source = PassageSource.objects.create(
            title="Sample", content="One.\n\nTwo.", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(self.source, self.exam)

    def test_start_snapshots_text_and_exam_rules(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)
        self.assertEqual(attempt.reference_text, self.publication.rendered_content)
        self.assertEqual(attempt.rules_snapshot["allow_backspace"], False)
        self.assertEqual(attempt.duration_seconds, 600)
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(seconds=600))

    def test_source_edits_do_not_change_started_attempt(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        original = attempt.reference_text
        self.source.content = "Replaced later"
        self.source.save()
        attempt.refresh_from_db()
        self.assertEqual(attempt.reference_text, original)

    def test_submission_is_single_use(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(session_id=attempt.pk, learner=self.learner, typed_text="One.")
        self.assertEqual(result.state, TypingSession.State.SUBMITTED)
        self.assertEqual(result.submitted_text, "One.")
        with self.assertRaises(ValidationError):
            submit_session(session_id=attempt.pk, learner=self.learner, typed_text="Overwrite")

    def test_other_learner_cannot_submit(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(TypingSession.DoesNotExist):
            submit_session(session_id=attempt.pk, learner=self.other, typed_text="No")
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)

    def test_expired_attempt_is_not_marked_as_on_time(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        TypingSession.objects.filter(pk=attempt.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
        result = submit_session(session_id=attempt.pk, learner=self.learner, typed_text="Late")
        self.assertEqual(result.state, TypingSession.State.EXPIRED)

    def test_expire_requires_deadline(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(ValidationError):
            expire_session(session_id=attempt.pk, learner=self.learner)

    def test_archived_passage_cannot_start(self):
        self.publication.status = "ARCHIVED"
        self.publication.save(update_fields=("status",))
        with self.assertRaises(ValidationError):
            start_session(learner=self.learner, publication=self.publication)

    def test_unauthenticated_start_is_denied(self):
        with self.assertRaises(PermissionDenied):
            start_session(learner=None, publication=self.publication)

    def test_unverified_exam_does_not_claim_scoring(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.rules_snapshot["verification_status"], "UNVERIFIED")
        self.assertEqual(attempt.result_snapshot, {})
        self.assertEqual(attempt.scoring_version, "")
