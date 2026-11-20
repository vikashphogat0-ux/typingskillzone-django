from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from exams.models import ExamConfiguration
from passages.models import PassageSource, SimulatorPassage
from passages.scheduling import PER_DAY, apply_schedule, plan_schedule
from passages.services import publish_source_to_exam


class AutoSchedulerTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(
            code="auto-exam", name="Auto Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.start = timezone.localdate() + timedelta(days=1)
        for index in range(13):
            source = PassageSource.objects.create(
                title=f"Auto {index}", content="Text.", language="ENGLISH", script="LATIN",
                status=PassageSource.Status.PUBLISHED,
            )
            publish_source_to_exam(source, self.exam)

    def test_plan_fills_slots_in_order_twelve_per_day(self):
        plan = plan_schedule(self.exam, self.start)
        self.assertEqual(len(plan), 13)
        first_day = [item for item in plan if item[1] == self.start]
        self.assertEqual(len(first_day), PER_DAY)
        self.assertEqual(first_day[0][2:], ("MORNING", 1))
        self.assertEqual(first_day[5][2:], ("AFTERNOON", 1))
        self.assertEqual(first_day[-1][2:], ("EVENING", 2))
        self.assertEqual(plan[-1][1], self.start + timedelta(days=1))

    def test_apply_writes_schedule_and_keeps_upload_order(self):
        apply_schedule(plan_schedule(self.exam, self.start))
        first = SimulatorPassage.objects.get(exam=self.exam, serial_number=1)
        self.assertEqual(first.release_date, self.start)
        self.assertEqual(first.release_slot, "MORNING")
        self.assertEqual(first.release_position, 1)

    def test_already_scheduled_passages_are_not_moved(self):
        apply_schedule(plan_schedule(self.exam, self.start))
        self.assertEqual(plan_schedule(self.exam, self.start + timedelta(days=5)), [])

    def test_overlapping_start_is_refused(self):
        apply_schedule(plan_schedule(self.exam, self.start))
        extra = PassageSource.objects.create(
            title="Late upload", content="Text.", language="ENGLISH", script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        publish_source_to_exam(extra, self.exam)
        with self.assertRaises(ValueError):
            plan_schedule(self.exam, self.start)

    def test_command_is_dry_run_by_default(self):
        out = StringIO()
        call_command("auto_schedule_passages", "--exam", "auto-exam", stdout=out)
        self.assertFalse(SimulatorPassage.objects.filter(exam=self.exam, release_date__isnull=False).exists())
        self.assertIn("Dry run only", out.getvalue())

    def test_command_apply_writes(self):
        call_command("auto_schedule_passages", "--exam", "auto-exam", "--apply", stdout=StringIO())
        self.assertEqual(SimulatorPassage.objects.filter(exam=self.exam, release_date__isnull=False).count(), 13)

    def test_admin_page_requires_superuser_and_renders(self):
        self.assertEqual(self.client.get(reverse("admin:passages_autoschedule")).status_code, 302)
        admin = get_user_model().objects.create_superuser(email="auto-admin@example.com", password="AdminStrong123!")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:passages_autoschedule"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auto Exam")
