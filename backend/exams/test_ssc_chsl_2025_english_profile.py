from django.core.management import call_command
from django.test import TestCase

from exams.models import ExamConfiguration


class SSCCHSL2025EnglishProfileTests(TestCase):
    def test_configuration_command_updates_only_the_named_chsl_profile(self):
        exam = ExamConfiguration.objects.create(
            code="ssc-chsl-2025-english-test-tcs-interface",
            name="SSC CHSL 2025 English Test (TCS Interface)",
        )
        other = ExamConfiguration.objects.create(
            code="ssc-chsl-2025-hindi-kurtidev",
            name="SSC CHSL 2025 Hindi (KurtiDev)",
        )

        call_command("configure_ssc_chsl_2025_english")

        exam.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(exam.duration_seconds, 600)
        self.assertEqual(exam.minimum_wpm, 35)
        self.assertEqual(exam.required_keystrokes, 1750)
        self.assertEqual(exam.backspace_policy, ExamConfiguration.BackspacePolicy.FULL)
        self.assertFalse(exam.allow_paste)
        self.assertFalse(exam.allow_copy)
        self.assertEqual(exam.scoring_rules["formula"], "SSC_CHSL_2025_ENGLISH")
        self.assertEqual(exam.scoring_rules["category_error_caps"]["UR"], 7)
        self.assertEqual(exam.scoring_rules["category_error_caps"]["SC"], 10)
        self.assertEqual(exam.scoring_rules["compensatory_duration_seconds"], 900)
        self.assertEqual(exam.verification_status, ExamConfiguration.Verification.PARTIAL)

        # A sibling CHSL language/layout profile must remain untouched.
        self.assertIsNone(other.duration_seconds)
        self.assertEqual(other.scoring_mode, ExamConfiguration.ScoringMode.GENERIC)
