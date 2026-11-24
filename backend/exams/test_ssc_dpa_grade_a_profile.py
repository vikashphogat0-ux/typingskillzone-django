from django.core.management import call_command
from django.test import TestCase

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam
from typing_sessions.services import start_session
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


class SSCDataProcessingAssistantGradeAProfileTests(TestCase):
    def setUp(self):
        self.exam = ExamConfiguration.objects.create(
            code="ssc-data-processing-assistant-grade-a",
            name="SSC Data Processing Assistant Grade-A",
        )

    def test_configuration_command_applies_only_dpa_profile_values(self):
        call_command("configure_ssc_dpa_grade_a")
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.duration_seconds, 900)
        self.assertEqual(self.exam.trial_seconds, 300)
        self.assertEqual(self.exam.required_keystrokes, 3750)
        self.assertEqual(self.exam.minimum_wpm, 50)
        self.assertEqual(self.exam.scoring_rules["formula"], "SSC_DPA_GRADE_A")
        self.assertEqual(self.exam.verification_status, ExamConfiguration.Verification.VERIFIED)
        self.assertFalse(self.exam.allow_paste)
        self.assertTrue(self.exam.allow_backspace)
        self.assertFalse(self.exam.allow_passage_repeat)

    def test_dpa_session_tab_indents_each_paragraph_and_checks_passage_length(self):
        call_command("configure_ssc_dpa_grade_a")
        self.exam.refresh_from_db()
        User = get_user_model()
        learner = User.objects.create_user(
            email="dpa-learner@example.test",
            password="SafePassword123!",
        )
        first = "alpha " * 350
        second = "beta " * 350
        content = first.strip() + "\n\n" + second.strip()
        self.assertGreaterEqual(len(content), 3700)
        self.assertLessEqual(len(content), 4000)
        source = PassageSource.objects.create(
            title="DPA passage",
            content=content,
            language="ENGLISH",
            script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        publication = publish_source_to_exam(source, self.exam)
        session = start_session(learner=learner, publication=publication)
        self.assertTrue(session.reference_text.startswith("\t"))
        self.assertIn("\n\n\t", session.reference_text)

    def test_dpa_session_rejects_passage_outside_configured_character_range(self):
        call_command("configure_ssc_dpa_grade_a")
        self.exam.refresh_from_db()
        User = get_user_model()
        learner = User.objects.create_user(
            email="dpa-short@example.test",
            password="SafePassword123!",
        )
        source = PassageSource.objects.create(
            title="Short DPA passage",
            content="This passage is intentionally too short.",
            language="ENGLISH",
            script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        publication = publish_source_to_exam(source, self.exam)
        with self.assertRaises(ValidationError):
            start_session(learner=learner, publication=publication)
