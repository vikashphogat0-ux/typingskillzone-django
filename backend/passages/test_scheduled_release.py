from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from exams.models import ExamConfiguration
from passages.models import LOCAL_TZ, PassageSource, SimulatorPassage, released_queryset
from passages.services import publish_source_to_exam


class ScheduledReleaseTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(
            code="sched-exam", name="Scheduled Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        source = PassageSource.objects.create(
            title="Scheduled source", content="One.\n\nTwo.", language="ENGLISH", script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        self.passage = publish_source_to_exam(source, self.exam)
        self.today = timezone.localdate()

    def test_unscheduled_passage_is_always_released(self):
        self.assertIsNone(self.passage.release_at)
        self.assertTrue(self.passage.is_released())

    def test_morning_slot_opens_at_seven(self):
        self.passage.release_date = self.today
        self.passage.release_slot = "MORNING"
        self.passage.release_position = 1
        before = datetime.combine(self.today, datetime.min.time(), tzinfo=LOCAL_TZ).replace(hour=6, minute=59)
        after = before.replace(hour=7, minute=0, second=1)
        self.assertFalse(self.passage.is_released(now=before))
        self.assertTrue(self.passage.is_released(now=after))

    def test_released_queryset_hides_future_slots(self):
        self.passage.release_date = self.today
        self.passage.release_slot = "EVENING"
        self.passage.release_position = 1
        self.passage.save()
        early = datetime.combine(self.today, datetime.min.time(), tzinfo=LOCAL_TZ).replace(hour=8)
        late = early.replace(hour=20)
        self.assertNotIn(self.passage, released_queryset(SimulatorPassage.objects.all(), now=early))
        self.assertIn(self.passage, released_queryset(SimulatorPassage.objects.all(), now=late))

    def test_detail_page_hidden_until_release(self):
        self.passage.release_date = self.today + timedelta(days=1)
        self.passage.release_slot = "MORNING"
        self.passage.release_position = 1
        self.passage.save()
        response = self.client.get(reverse("passages:simulator-detail", args=[self.exam.code, self.passage.passage_id]))
        self.assertEqual(response.status_code, 404)

    def test_slot_capacity_is_enforced(self):
        self.passage.release_date = self.today
        self.passage.release_slot = "EVENING"
        self.passage.release_position = 3
        with self.assertRaises(ValidationError):
            self.passage.clean()

    def test_partial_schedule_is_rejected(self):
        self.passage.release_date = self.today
        with self.assertRaises(ValidationError):
            self.passage.clean()
