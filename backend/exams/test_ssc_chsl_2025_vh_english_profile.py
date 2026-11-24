from django.core.management import call_command
from django.test import TestCase

from exams.models import ExamConfiguration


class SSCCHSL2025VHEnglishProfileTests(TestCase):
    def test_command_applies_complete_internal_user_verified_profile(self):
        exam = ExamConfiguration.objects.create(
            code="ssc-chsl-2025-vh-category-english",
            name="SSC CHSL 2025 VH Category English",
        )
        sibling = ExamConfiguration.objects.create(
            code="ssc-chsl-2025-english-test-tcs-interface",
            name="SSC CHSL 2025 English Test (TCS Interface)",
        )

        call_command("configure_ssc_chsl_2025_vh_english")

        exam.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(exam.verification_status, ExamConfiguration.Verification.VERIFIED)
        self.assertTrue(exam.source_title.startswith("Internal rule profile:"))
        self.assertIsNotNone(exam.source_checked_at)
        self.assertEqual(exam.duration_seconds, 900)
        self.assertEqual(exam.minimum_wpm, 35)
        self.assertEqual(exam.required_keystrokes, 2625)
        self.assertEqual(exam.error_allowance_percent, 10)
        self.assertEqual(exam.backspace_policy, ExamConfiguration.BackspacePolicy.FULL)
        self.assertEqual(exam.scoring_rules["profile_variant"], "VH_CATEGORY_ENGLISH")
        self.assertEqual(exam.scoring_rules["formula"], "SSC_CHSL_2025_VH_ENGLISH")
        self.assertEqual(exam.scoring_rules["passage_word_range"], {"minimum": 350, "maximum": 400})
        self.assertEqual(exam.scoring_rules["category_error_caps"]["PWD"], 10)
        self.assertTrue(exam.scoring_rules["qualifying_only"])
        self.assertEqual(exam.qualification_rules["maximum_error_percent"], 10)\n        self.assertEqual(exam.scoring_rules["scoring_duration_seconds"], 900)\n        self.assertEqual(exam.scoring_rules["minimum_strokes"], 2625)
        self.assertIn("INTERNAL SOURCE — USER VERIFIED", exam.rule_notes)

        # This command must not rewrite the standard CHSL English profile.
        self.assertIsNone(sibling.duration_seconds)
        self.assertEqual(sibling.verification_status, ExamConfiguration.Verification.UNVERIFIED)
