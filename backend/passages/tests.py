from django.contrib.auth import get_user_model
from django.test import TestCase

from exams.models import ExamConfiguration
from .models import PassageSource, SimulatorPassage
from .services import publish_source_to_exam, publish_source_to_selected_exams

User = get_user_model()


class CentralPassagePublishingTests(TestCase):
    def make_exam(self, code, name, language="ENGLISH", passage_format="PARAGRAPHS", script="LATIN"):
        return ExamConfiguration.objects.create(
            code=code,
            name=name,
            language=language,
            script=script,
            passage_format=passage_format,
        )

    def make_source(self, **kwargs):
        defaults = {
            "title": "Central source",
            "content": "First paragraph.\n\nSecond paragraph.",
            "language": "ENGLISH",
            "script": "LATIN",
        }
        defaults.update(kwargs)
        return PassageSource.objects.create(**defaults)

    def test_same_source_published_to_multiple_simulators_gets_independent_ids(self):
        source = self.make_source()
        delhi = self.make_exam("delhi-police-hcm", "Delhi Police HCM")
        bsf = self.make_exam("bsf-hcm", "BSF HCM")
        first = publish_source_to_exam(source, delhi)
        second = publish_source_to_exam(source, bsf)
        self.assertEqual(first.passage_id, "01")
        self.assertEqual(second.passage_id, "01")

    def test_next_ids_increment_independently_per_exam(self):
        source_a = self.make_source(title="A")
        source_b = self.make_source(title="B")
        delhi = self.make_exam("delhi-police-hcm", "Delhi Police HCM")
        bsf = self.make_exam("bsf-hcm", "BSF HCM")
        self.assertEqual(publish_source_to_exam(source_a, delhi).passage_id, "01")
        self.assertEqual(publish_source_to_exam(source_b, delhi).passage_id, "02")
        self.assertEqual(publish_source_to_exam(source_a, bsf).passage_id, "01")

    def test_republishing_same_source_does_not_duplicate_or_renumber(self):
        source = self.make_source()
        exam = self.make_exam("delhi-police-hcm", "Delhi Police HCM")
        first = publish_source_to_exam(source, exam)
        again = publish_source_to_exam(source, exam)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(again.passage_id, "01")

    def test_language_mismatch_is_rejected(self):
        source = self.make_source(language="HINDI", script="DEVANAGARI")
        exam = self.make_exam("delhi-police-hcm", "Delhi Police HCM", language="ENGLISH", script="LATIN")
        with self.assertRaises(ValueError):
            publish_source_to_exam(source, exam)
        self.assertEqual(SimulatorPassage.objects.count(), 0)

    def test_exam_formatting_does_not_modify_central_source(self):
        source = self.make_source()
        continuous = self.make_exam("continuous-test", "Continuous Test", passage_format="CONTINUOUS")
        paragraphs = self.make_exam("paragraph-test", "Paragraph Test", passage_format="PARAGRAPHS")
        continuous_publication = publish_source_to_exam(source, continuous)
        paragraph_publication = publish_source_to_exam(source, paragraphs)
        self.assertEqual(continuous_publication.rendered_content, "First paragraph. Second paragraph.")
        self.assertEqual(paragraph_publication.rendered_content, "First paragraph.\n\nSecond paragraph.")
        source.refresh_from_db()
        self.assertEqual(source.content, "First paragraph.\n\nSecond paragraph.")

    def test_bulk_distribution_uses_same_allocator(self):
        source = self.make_source()
        first = self.make_exam("exam-one", "Exam One")
        second = self.make_exam("exam-two", "Exam Two")
        source.target_exams.add(first, second)
        published = publish_source_to_selected_exams(source)
        self.assertEqual([item.passage_id for item in published], ["01", "01"])

