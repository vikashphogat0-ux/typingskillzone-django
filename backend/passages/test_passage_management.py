from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import auto_target_and_publish, matching_exams


class PassageManagementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(email="passage-admin@example.com", password="AdminStrong123!")
        self.english_a = ExamConfiguration.objects.create(code="eng-a", name="English A", language="ENGLISH", script="LATIN", duration_seconds=600, allow_backspace=False)
        self.english_b = ExamConfiguration.objects.create(code="eng-b", name="English B", language="ENGLISH", script="", duration_seconds=600, allow_backspace=False)
        self.hindi = ExamConfiguration.objects.create(code="hin", name="Hindi Exam", language="HINDI", script="DEVANAGARI", duration_seconds=600, allow_backspace=False)
        self.source = PassageSource.objects.create(title="Daily passage", content="One.\n\nTwo.", language="ENGLISH", script="LATIN", status=PassageSource.Status.DRAFT)

    def test_matching_exams_respects_language_and_script(self):
        names = {exam.name for exam in matching_exams(self.source)}
        self.assertEqual(names, {"English A", "English B"})

    def test_auto_target_publishes_to_every_matching_exam_only(self):
        publications = auto_target_and_publish(self.source)
        self.assertEqual(len(publications), 2)
        self.assertFalse(self.hindi.published_passages.exists())

    def test_studio_requires_superuser(self):
        self.assertEqual(self.client.get(reverse("admin:passages_studio")).status_code, 302)

    def test_studio_and_preview_render_for_admin(self):
        self.client.force_login(self.admin)
        studio = self.client.get(reverse("admin:passages_studio"))
        self.assertEqual(studio.status_code, 200)
        self.assertContains(studio, "English A")
        preview = self.client.get(reverse("admin:passages_preview", args=[self.source.pk]))
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Daily passage")
