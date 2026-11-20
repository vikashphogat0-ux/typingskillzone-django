from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from exams.models import ExamConfiguration
from passages.bulk import import_passages, parse_passage_csv
from passages.models import PassageSource, SimulatorPassage


def csv_file(text, name="passages.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class BulkUploadTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(
            code="bulk-english", name="Bulk English", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.admin = get_user_model().objects.create_superuser(email="bulk-admin@example.com", password="AdminStrong123!")

    def test_valid_file_parses_every_row(self):
        upload = csv_file("title,content,language\nOne,Text one.,english\nTwo,Text two.,ENGLISH\n")
        rows, errors = parse_passage_csv(upload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["language"], "ENGLISH")

    def test_bad_rows_are_reported_with_line_numbers(self):
        upload = csv_file("title,content,language\nOne,Text.,ENGLISH\n,Missing title,ENGLISH\nThree,Text.,FRENCH\n")
        rows, errors = parse_passage_csv(upload)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any(line.startswith("Row 3:") for line in errors))
        self.assertTrue(any(line.startswith("Row 4:") for line in errors))

    def test_missing_columns_stop_the_import(self):
        rows, errors = parse_passage_csv(csv_file("title,language\nOne,ENGLISH\n"))
        self.assertEqual(rows, [])
        self.assertIn("content", errors[0])

    def test_import_creates_publishes_and_schedules(self):
        rows, _ = parse_passage_csv(csv_file("title,content,language,script\nA,Text a.,ENGLISH,LATIN\nB,Text b.,ENGLISH,LATIN\nC,Text c.,ENGLISH,LATIN\n"))
        start = timezone.localdate() + timedelta(days=1)
        result = import_passages(rows, self.admin, publish=True, start_date=start)
        self.assertEqual(result["created"], 3)
        self.assertEqual(result["published"], 3)
        self.assertEqual(result["scheduled"], 3)
        first = SimulatorPassage.objects.get(exam=self.exam, serial_number=1)
        self.assertEqual(first.release_date, start)

    def test_ten_passages_publish_to_many_exams_with_independent_sequences(self):
        self.exam.is_active = False
        self.exam.save(update_fields=["is_active"])
        exams = [
            ExamConfiguration.objects.create(
                code=f"bulk-wide-{index:03d}",
                name=f"Bulk Wide {index:03d}",
                language="ENGLISH",
                script="LATIN",
                duration_seconds=600,
                allow_backspace=False,
            )
            for index in range(12)
        ]
        csv_rows = ["title,content,language,script"]
        csv_rows.extend(
            f"Wide {index},Passage content {index}.,ENGLISH,LATIN"
            for index in range(10)
        )
        rows, errors = parse_passage_csv(csv_file("\n".join(csv_rows) + "\n"))
        self.assertEqual(errors, [])

        result = import_passages(rows, self.admin, publish=True, start_date=None)

        self.assertEqual(result["created"], 10)
        self.assertEqual(result["published"], 120)
        self.assertEqual(
            SimulatorPassage.objects.filter(exam__in=exams, status=SimulatorPassage.Status.PUBLISHED).count(),
            120,
        )
        for exam in exams:
            self.assertEqual(
                list(SimulatorPassage.objects.filter(exam=exam).order_by("serial_number").values_list("serial_number", flat=True)),
                list(range(1, 11)),
            )

    def test_retry_resumes_same_users_partially_published_source(self):
        source = PassageSource.objects.create(
            title="Resume me",
            content="Resume passage.",
            language="ENGLISH",
            script="LATIN",
            created_by=self.admin,
            status=PassageSource.Status.PUBLISHED,
        )
        rows, _ = parse_passage_csv(
            csv_file("title,content,language,script\nResume me,Resume passage.,ENGLISH,LATIN\n")
        )

        first = import_passages(rows, self.admin, publish=True, start_date=None)
        second = import_passages(rows, self.admin, publish=True, start_date=None)

        self.assertEqual(first["created"], 0)
        self.assertEqual(first["published"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["published"], 0)
        self.assertEqual(SimulatorPassage.objects.filter(source=source).count(), 1)

    def test_existing_title_is_skipped(self):
        PassageSource.objects.create(title="Dup", content="x", language="ENGLISH", script="LATIN")
        rows, _ = parse_passage_csv(csv_file("title,content,language\nDup,Text.,ENGLISH\n"))
        result = import_passages(rows, self.admin, publish=False, start_date=None)
        self.assertEqual(result["created"], 0)
        self.assertEqual(len(result["skipped"]), 1)

    def test_page_requires_superuser(self):
        self.assertEqual(self.client.get(reverse("admin:passages_bulk")).status_code, 302)

    def test_preview_then_import_through_the_page(self):
        self.client.force_login(self.admin)
        preview = self.client.post(reverse("admin:passages_bulk"), {
            "action": "preview", "publish": "1", "file": csv_file("title,content,language,script\nP,Text p.,ENGLISH,LATIN\n"),
        })
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Review 1 valid passage")
        imported = self.client.post(reverse("admin:passages_bulk"), {"action": "import"})
        self.assertEqual(imported.status_code, 200)
        self.assertTrue(PassageSource.objects.filter(title="P").exists())
