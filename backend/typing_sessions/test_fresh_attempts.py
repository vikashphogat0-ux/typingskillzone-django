from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam
from typing_sessions.models import TypingSession


class FreshAttemptTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(code="fresh-exam", name="Fresh Exam", language="ENGLISH", script="LATIN", duration_seconds=600, allow_backspace=False)
        source = PassageSource.objects.create(title="Fresh source", content="One two three.", language="ENGLISH", script="LATIN", status=PassageSource.Status.PUBLISHED)
        self.publication = publish_source_to_exam(source, self.exam)
        self.student = get_user_model().objects.create_user(email="fresh-student@example.com", password="SafePassword123!", is_active=True, is_email_verified=True)
        self.client.force_login(self.student)
        self.start_url = reverse("typing_sessions:start", args=[self.exam.code, self.publication.passage_id])

    def test_start_opens_the_test_then_refresh_returns_to_passage_page(self):
        response = self.client.post(self.start_url, {"display_mode": "highlighted"})
        attempt = TypingSession.objects.get(learner=self.student, publication=self.publication)
        self.assertEqual(self.client.get(response.url).status_code, 200)
        refreshed = self.client.get(response.url)
        self.assertEqual(refreshed.status_code, 302)
        self.assertIn(f"/simulators/{self.exam.code}/passages/", refreshed.url)
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.EXPIRED)
        self.assertEqual(attempt.result_snapshot, {})

    def test_each_start_gets_its_own_mode_and_timer(self):
        self.client.post(self.start_url, {"display_mode": "offscreen"})
        self.client.post(self.start_url, {"display_mode": "normal"})
        active = TypingSession.objects.get(learner=self.student, state=TypingSession.State.ACTIVE)
        self.assertEqual(active.rules_snapshot["display_mode"], "normal")
        self.assertIsNone(active.deadline_at)
