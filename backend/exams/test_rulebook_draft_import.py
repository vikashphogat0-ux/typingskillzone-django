from django.test import SimpleTestCase

from exams.management.commands.import_exam_rulebook_profiles import (
    _backspace_policy,
    _first_duration_seconds,
    build_draft_defaults,
)
from exams.models import ExamConfiguration


class RulebookDraftImportTests(SimpleTestCase):
    def test_duration_is_extracted_without_guessing(self):
        self.assertEqual(_first_duration_seconds(["Duration & Target: 10 minutes • 35 WPM"]), 600)
        self.assertIsNone(_first_duration_seconds(["Duration varies by notification."]))

    def test_ambiguous_backspace_is_not_guessed(self):
        result = _backspace_policy(["Interface: Backspace behavior depends on centre instructions."])
        self.assertEqual(result, ExamConfiguration.BackspacePolicy.NOT_SPECIFIED)

    def test_disabled_backspace_is_preserved(self):
        result = _backspace_policy(["Interface: Backspace disabled."])
        self.assertEqual(result, ExamConfiguration.BackspacePolicy.DISABLED)

    def test_imported_profile_is_inactive_and_source_rules_are_non_executable(self):
        profile = {
            "number": 1,
            "profile_id": "rrb-example-en-001",
            "name": "RRB Example English",
            "source_text": [
                "Exam Pattern & Qualifying Nature: Qualifying.",
                "Duration & Target: 10 minutes • 30 WPM.",
                "Interface, Passage & Keyboard Rules: Backspace disabled.",
                "WPM & Error Formula:",
                '"Net WPM"=(words - mistakes)/10',
                "Qualifying Criteria: At least 30 Net WPM.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertFalse(defaults["is_active"])
        self.assertEqual(defaults["duration_seconds"], 600)
        self.assertEqual(defaults["backspace_policy"], ExamConfiguration.BackspacePolicy.DISABLED)
        self.assertFalse(defaults["scoring_rules"]["executable"])
        self.assertFalse(defaults["qualification_rules"]["executable"])


    def test_explicit_tcs_layout_and_keyboard_hints_are_extracted(self):
        profile = {
            "number": 1,
            "profile_id": "ssc-chsl-example",
            "name": "SSC CHSL Hindi (Mangal Font)",
            "source_text": [
                "Duration & Target: 10 minutes • 30 WPM (9,000 KDPH / ~1,500 key depressions in 10 minutes).",
                "Interface, Passage & Keyboard Rules: TCS iON split-screen with Mangal (Inscript / Remington Gail) layout. Backspace is allowed; copy/paste disabled.",
                "Qualifying Criteria: Meet the applicable benchmark.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["duration_seconds"], 600)
        self.assertEqual(defaults["minimum_wpm"], 30.0)
        self.assertEqual(defaults["required_keystrokes"], 1500)
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.TCS)
        self.assertEqual(defaults["passage_source_mode"], ExamConfiguration.PassageSourceMode.SCREEN)
        self.assertEqual(defaults["keyboard_layout"], "Remington Gail")
        self.assertFalse(defaults["allow_copy"])
        self.assertFalse(defaults["allow_paste"])
        self.assertFalse(defaults["is_active"])

    def test_notification_dependent_or_multiple_wpm_values_are_not_collapsed(self):
        profile = {
            "number": 2,
            "profile_id": "conditional-example",
            "name": "State Typing English",
            "source_text": [
                "Duration & Target: 10 minutes • 30–35 WPM depending on post.",
                "Interface, Passage & Keyboard Rules: English QWERTY.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertIsNone(defaults["minimum_wpm"])
        self.assertEqual(defaults["keyboard_layout"], "QWERTY")
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.UNCONFIGURED)
