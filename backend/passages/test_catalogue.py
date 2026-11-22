from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from exams.models import ExamConfiguration

User = get_user_model()


class SimulatorCatalogueTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="catalogue-learner@example.com",
            password="SafePass!234",
        )
        self.ssc_exam = ExamConfiguration.objects.create(
            code="ssc-practice-english",
            name="SSC Practice English Test",
            category=ExamConfiguration.Category.SSC,
            language="ENGLISH",
            script="LATIN",
            display_order=1,
        )
        self.hindi_exam = ExamConfiguration.objects.create(
            code="court-hindi-test",
            name="District Court Hindi Test",
            category=ExamConfiguration.Category.COURT,
            language="HINDI",
            script="MANGAL",
            display_order=2,
        )
        ExamConfiguration.objects.create(
            code="hidden-inactive-exam",
            name="Inactive Catalogue Entry",
            category=ExamConfiguration.Category.OTHER,
            is_active=False,
        )

    def test_catalogue_requires_login(self):
        response = self.client.get(reverse("passages:simulator-catalogue"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_catalogue_lists_all_active_exams_and_preserves_existing_exam_routes(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-catalogue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ssc_exam.name)
        self.assertContains(response, self.hindi_exam.name)
        self.assertNotContains(response, "Inactive Catalogue Entry")
        self.assertContains(
            response,
            reverse("passages:simulator-list", args=[self.ssc_exam.code]),
        )
        self.assertContains(
            response,
            reverse("passages:simulator-list", args=[self.hindi_exam.code]),
        )

    def test_catalogue_groups_exams_by_stored_category(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-catalogue"))

        self.assertContains(response, 'data-exam-section="SSC"')
        self.assertContains(response, 'data-exam-section="COURT"')
        self.assertContains(response, "Exam Categories")
        self.assertContains(response, "All Exams")

    def test_catalogue_search_metadata_is_rendered_for_client_side_filtering(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-catalogue"))

        self.assertContains(
            response,
            'data-search="ssc practice english test ssc-practice-english english latin',
        )
        self.assertContains(response, "Search exam by name (e.g. SSC, BSF, Court, Beltron)")

    def test_catalogue_includes_live_search_highlighting_and_clear_control(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-catalogue"))

        self.assertContains(response, 'id="clearExamSearch"')
        self.assertContains(response, 'data-highlight-text')
        self.assertContains(response, 'mark.exam-match')
        self.assertContains(response, 'addEventListener("input", applySearch)')

    def test_category_navigation_targets_matching_exam_section(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("passages:simulator-catalogue"))

        self.assertContains(response, 'id="exam-category-SSC"')
        self.assertContains(response, 'data-category-filter="SSC"')
        self.assertContains(response, 'scrollIntoView({behavior: "smooth", block: "start"})')
        self.assertContains(response, 'id="examSectionsPanel"')

    def test_public_homepage_loads_without_authentication_and_links_existing_portals(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Build your typing speed with TypingSkillZone")
        self.assertContains(response, reverse("institutes:student_login"))
        self.assertContains(response, reverse("accounts:student_register"))
        self.assertContains(response, reverse("passages:simulator-catalogue"))
        self.assertContains(response, reverse("institutes:register"))
