from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration
from .models import PassageSource, SimulatorPassage
from .services import publish_source_to_exam, publish_source_to_selected_exams

User = get_user_model()


class CentralPassagePublishingTests(TestCase):
    def make_exam(self, code, name, language="ENGLISH", passage_format="CUSTOM", script="LATIN"):
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

    def test_archived_publication_keeps_its_id_and_next_id_advances(self):
        source_a = self.make_source(title="A")
        source_b = self.make_source(title="B")
        exam = self.make_exam("archive-test", "Archive Test")
        first = publish_source_to_exam(source_a, exam)
        first.status = SimulatorPassage.Status.ARCHIVED
        first.save(update_fields=("status",))
        second = publish_source_to_exam(source_b, exam)
        self.assertEqual(first.passage_id, "01")
        self.assertEqual(second.passage_id, "02")

    def test_bulk_distribution_uses_same_allocator(self):
        source = self.make_source()
        first = self.make_exam("exam-one", "Exam One")
        second = self.make_exam("exam-two", "Exam Two")
        source.target_exams.add(first, second)
        published = publish_source_to_selected_exams(source)
        self.assertEqual([item.passage_id for item in published], ["01", "01"])

    def test_simulator_passage_pages_require_login(self):
        exam = self.make_exam("delhi-police-hcm", "Delhi Police HCM")
        response = self.client.get(reverse("passages:simulator-list", args=[exam.code]))
        self.assertEqual(response.status_code, 302)

    def test_simulator_passage_list_shows_exam_local_serial(self):
        user = User.objects.create_user(email="learner@example.com", password="SafePass!234")
        self.client.force_login(user)
        source = self.make_source()
        exam = self.make_exam("delhi-police-hcm", "Delhi Police HCM")
        publish_source_to_exam(source, exam)
        response = self.client.get(reverse("passages:simulator-list", args=[exam.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "01")
        self.assertContains(response, "Central source")



    def test_simulator_specific_layout_profiles_render_independently(self):
        source = self.make_source(content="  First line.\nSecond line.\n\n\tIndented item.  ")
        continuous = self.make_exam("layout-continuous", "Continuous")
        continuous.passage_layout = ExamConfiguration.PassageLayout.CONTINUOUS
        continuous.save()
        para_tab = self.make_exam("layout-para-tab", "Para Tab")
        para_tab.passage_layout = ExamConfiguration.PassageLayout.PARA_TAB
        para_tab.passage_preserve_tabs = True
        para_tab.passage_tab_size = 6
        para_tab.save()
        first = publish_source_to_exam(source, continuous)
        second = publish_source_to_exam(source, para_tab)
        self.assertEqual(first.rendered_content, "First line. Second line. Indented item.")
        self.assertIn("\tIndented item.", second.rendered_content)
        self.assertEqual(second.exam.passage_tab_size, 6)
        source.refresh_from_db()
        self.assertEqual(source.content, "  First line.\nSecond line.\n\n\tIndented item.  ")

    def test_unconfigured_layout_preserves_original_text(self):
        source = self.make_source(content="Line one.\n\n    Line two.")
        exam = self.make_exam("layout-pending", "Pending Format")
        exam.passage_layout = ExamConfiguration.PassageLayout.UNCONFIGURED
        exam.save()
        publication = publish_source_to_exam(source, exam)
        self.assertEqual(publication.rendered_content, "Line one.\n\n    Line two.")

    def test_paragraph_blocks_are_available_for_spacing_aware_template(self):
        source = self.make_source(content="First paragraph.\n\nSecond paragraph.")
        exam = self.make_exam("layout-paragraphs", "Paragraph Layout")
        exam.passage_layout = ExamConfiguration.PassageLayout.PARAGRAPHS
        exam.save()
        publication = publish_source_to_exam(source, exam)
        self.assertEqual(publication.rendered_paragraphs, ["First paragraph.", "Second paragraph."])


class PublicHomepageAndRedirectTests(TestCase):
    def test_public_homepage_renders_with_student_and_institute_portal_links(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "passages/home.html")
        self.assertContains(response, "Build typing speed, accuracy and exam confidence.")
        self.assertContains(response, reverse("institutes:student_login"))
        self.assertContains(response, reverse("accounts:student_register"))
        self.assertContains(response, reverse("institutes:owner_login"))

    def test_anonymous_student_simulator_redirects_to_student_login_portal(self):
        exam = ExamConfiguration.objects.create(
            code="redirect-test",
            name="Redirect Test",
            language="ENGLISH",
            script="LATIN",
            passage_format="CUSTOM",
        )
        response = self.client.get(reverse("passages:simulator-list", args=[exam.code]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url.split("?", 1)[0], reverse("institutes:student_login"))

