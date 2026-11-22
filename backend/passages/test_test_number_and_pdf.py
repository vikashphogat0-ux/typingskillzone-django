from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.pdf import build_passage_pdf, UnsupportedScript
from passages.services import publish_source_to_exam


class TestNumberAndPdfTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(code="pdf-exam", name="PDF Exam", language="ENGLISH", script="LATIN", duration_seconds=600, allow_backspace=False)
        source = PassageSource.objects.create(title="Sheet passage", content="First paragraph here.\n\nSecond paragraph here.", language="ENGLISH", script="LATIN", status=PassageSource.Status.PUBLISHED)
        self.publication = publish_source_to_exam(source, self.exam)
        self.student = get_user_model().objects.create_user(email="pdf-student@example.com", password="SafePassword123!", is_active=True, is_email_verified=True)

    def test_test_number_has_the_tsz_prefix(self):
        self.assertTrue(self.publication.test_number.startswith("TSZ-"))

    def test_pdf_downloads_as_pdf(self):
        self.client.force_login(self.student)
        url = reverse("passages:simulator-pdf", args=[self.exam.code, self.publication.passage_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(self.publication.test_number, response["Content-Disposition"])

    def test_hindi_text_is_refused_clearly(self):
        with self.assertRaises(UnsupportedScript):
            build_passage_pdf(test_number="TSZ-00001", exam_name="Hindi", title="x", paragraphs=["\u0915\u092e\u0932"])

    def test_passage_page_shows_number_and_download(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-detail", args=[self.exam.code, self.publication.passage_id]))
        self.assertContains(response, self.publication.test_number)
        self.assertContains(response, "Download PDF")
