from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from passages.models import PassageSource, SimulatorPassage


class PassageLibraryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(
            email="library-student@example.test",
            password="StudentStrong123!",
            role=User.Roles.STUDENT,
            is_active=True,
        )
        self.exam = ExamConfiguration.objects.create(
            code="library-ssc",
            name="SSC Typing Test",
            language="ENGLISH",
            script="LATIN",
            duration_seconds=600,
            allow_backspace=True,
        )
        self.other_exam = ExamConfiguration.objects.create(
            code="library-court",
            name="Court Typing Test",
            language="ENGLISH",
            script="LATIN",
            duration_seconds=600,
            allow_backspace=True,
        )
        self.source = PassageSource.objects.create(
            title="Library passage",
            content="First paragraph.\n\nSecond paragraph.",
            language="ENGLISH",
            script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        self.publication = SimulatorPassage.objects.create(
            exam=self.exam,
            source=self.source,
            serial_number=1,
            status=SimulatorPassage.Status.PUBLISHED,
        )
        self.client.force_login(self.student)

    def test_library_requires_exam_selection_before_showing_passages(self):
        response = self.client.get(reverse("accounts:passage_library"))

        self.assertRedirects(response, reverse("exams:catalogue"), fetch_redirect_response=False)

    def test_selected_exam_shows_only_its_passages(self):
        response = self.client.get(
            reverse("accounts:passage_library"), {"exam": self.exam.code}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["exam_selection"])
        self.assertEqual(response.context["passage_count"], 1)
        self.assertContains(response, "Library passage")
        self.assertNotContains(response, "Court Typing Test")

    def test_txt_download_preserves_passage_paragraphs(self):
        response = self.client.get(reverse(
            "accounts:download_library_passage",
            args=[self.exam.code, self.publication.passage_id, "txt"],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertIn("First paragraph.\n\nSecond paragraph.", response.content.decode("utf-8"))

    def test_pdf_download_returns_pdf_document(self):
        response = self.client.get(reverse(
            "accounts:download_library_passage",
            args=[self.exam.code, self.publication.passage_id, "pdf"],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_non_student_cannot_download_library_passages(self):
        admin = get_user_model().objects.create_superuser(
            email="library-admin@example.test", password="AdminStrong123!"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse(
            "accounts:download_library_passage",
            args=[self.exam.code, self.publication.passage_id, "txt"],
        ))
        self.assertEqual(response.status_code, 403)
