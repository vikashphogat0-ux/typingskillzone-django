from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam


class ExamCatalogueTests(TestCase):
    def setUp(self):
        self.english = ExamConfiguration.objects.create(
            code="ssc-cgl-test", name="SSC CGL Typing Test", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.hindi = ExamConfiguration.objects.create(
            code="hindi-test", name="Hindi Typing Test", language="HINDI", script="DEVANAGARI",
            duration_seconds=900, allow_backspace=False,
        )
        self.inactive = ExamConfiguration.objects.create(
            code="retired-test", name="Retired Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False, is_active=False,
        )
        source = PassageSource.objects.create(
            title="Daily English passage", content="The quick brown fox.", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(source, self.english)

    def test_catalogue_lists_active_exams_only(self):
        response = self.client.get(reverse("exams:catalogue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SSC CGL Typing Test")
        self.assertContains(response, "Hindi Typing Test")
        self.assertNotContains(response, "Retired Exam")

    def test_search_filters_by_name(self):
        response = self.client.get(reverse("exams:catalogue"), {"q": "hindi"})
        self.assertContains(response, "Hindi Typing Test")
        self.assertNotContains(response, "SSC CGL Typing Test")

    def test_language_filter(self):
        response = self.client.get(reverse("exams:catalogue"), {"lang": "HINDI"})
        self.assertContains(response, "Hindi Typing Test")
        self.assertNotContains(response, "SSC CGL Typing Test")

    def test_exam_detail_shows_exam_scoped_passage_selector(self):
        from django.contrib.auth import get_user_model
        student = get_user_model().objects.create_user(
            email="exam-workspace-student@example.com", password="SafePassword123!",
            is_active=True,
        )
        self.client.force_login(student)
        response = self.client.get(reverse("exams:exam_detail", args=["ssc-cgl-test"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a passage for practice")
        self.assertContains(response, "Daily English passage")
        self.assertContains(response, 'name="passage_id"')
        self.assertContains(response, 'name="display_mode"')
        self.assertContains(response, "Start practice")

    def test_exam_detail_requires_student_login(self):
        response = self.client.get(reverse("exams:exam_detail", args=["ssc-cgl-test"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:student_login"), response.url)

    def test_inactive_exam_detail_is_not_found(self):
        from django.contrib.auth import get_user_model
        student = get_user_model().objects.create_user(
            email="inactive-exam-student@example.com", password="SafePassword123!",
            is_active=True,
        )
        self.client.force_login(student)
        response = self.client.get(reverse("exams:exam_detail", args=["retired-test"]))
        self.assertEqual(response.status_code, 404)

    def test_student_dashboard_links_to_catalogue(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            email="catalogue-student@example.com", password="SafePassword123!",
            is_active=True, is_email_verified=True,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertContains(response, reverse("exams:catalogue"))
