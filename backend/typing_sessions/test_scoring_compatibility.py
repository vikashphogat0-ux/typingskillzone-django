"""Regression contract for the legacy scoring engine.

These tests intentionally pin current behavior before introducing a canonical
exam-specification resolver. They are compatibility tests, not endorsements
that a formula is officially correct for any particular recruitment exam.
"""
from django.test import SimpleTestCase

from typing_sessions.scoring import SCORING_VERSION, calculate_result


class LegacyScoringCompatibilityTests(SimpleTestCase):
    def calculate(self, mode="GENERIC", **overrides):
        rules = {"scoring_mode": mode, **overrides}
        return calculate_result(
            reference="one two",
            typed="one too",
            duration_seconds=60,
            rules=rules,
        )

    def test_engine_version_is_pinned(self):
        self.assertEqual(SCORING_VERSION, "tsz-char-word-v1")

    def test_generic_metrics_are_stable(self):
        result = self.calculate()
        self.assertEqual(result["typed_characters"], 7)
        self.assertEqual(result["reference_characters"], 7)
        self.assertEqual(result["correct_characters"], 6)
        self.assertEqual(result["character_errors"], 2)
        self.assertEqual(result["word_errors"], 1)
        self.assertEqual(result["correct_words"], 1)
        self.assertEqual(result["gross_words"], 2)
        self.assertEqual(result["accuracy_percent"], 85.71)
        self.assertEqual(result["gross_wpm"], 1.4)
        self.assertEqual(result["correct_wpm"], 1.2)
        self.assertEqual(result["net_wpm"], 1.2)
        self.assertIsNone(result["score"])
        self.assertIsNone(result["qualification"])

    def test_word_error_switch_changes_error_unit(self):
        result = self.calculate(error_rules={"count_word_errors": True})
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["error_count_method"], "word")

    def test_correct_words_mode(self):
        result = self.calculate("CORRECT_WORDS")
        self.assertEqual(result["net_wpm"], 1.0)

    def test_net_wpm_mode_uses_typed_character_length(self):
        result = self.calculate(
            "NET_WPM",
            scoring_rules={"error_unit_strokes": 2},
        )
        self.assertEqual(result["net_wpm"], 1.0)

    def test_stroke_penalty_mode_uses_profile_penalty(self):
        result = self.calculate(
            "STROKE_PENALTY",
            strokes_per_word=5,
            mistake_penalty_strokes=2,
        )
        self.assertEqual(result["net_wpm"], 1.0)

    def test_correct_word_marks_mode(self):
        result = self.calculate(
            "CORRECT_WORD_MARKS",
            scoring_rules={"marks_per_correct_word": 3},
        )
        self.assertEqual(result["score"], 3.0)

    def test_error_percentage_mode_uses_gross_word_denominator(self):
        result = self.calculate(
            "ERROR_PERCENTAGE",
            error_allowance_percent=50,
            minimum_wpm=0,
            verification_status="VERIFIED",
        )
        self.assertEqual(result["permitted_error_count"], 1)
        self.assertEqual(result["excess_error_count"], 1)
        self.assertFalse(result["qualification"])

    def test_qualifying_only_mode_shares_error_percentage_behavior(self):
        result = self.calculate(
            "QUALIFYING_ONLY",
            error_allowance_percent=50,
            minimum_wpm=0,
            verification_status="VERIFIED",
        )
        self.assertFalse(result["qualification"])

    def test_custom_mode_penalty_and_score_band(self):
        result = self.calculate(
            "CUSTOM",
            error_rules={"count_word_errors": True},
            scoring_rules={
                "mistake_penalty_words": 1,
                "score_bands": [[1, 5]],
            },
        )
        self.assertEqual(result["net_words"], 1)
        self.assertEqual(result["net_wpm"], 1.0)
        self.assertEqual(result["score"], 5.0)

    def test_custom_disqualification_does_not_claim_unverified_failure(self):
        result = self.calculate(
            "CUSTOM",
            scoring_rules={"disqualify_at_mistakes": 1},
            verification_status="UNVERIFIED",
        )
        self.assertEqual(result["score"], 0)
        self.assertIsNone(result["qualification"])
        self.assertIn("not verified", result["qualification_note"])

    def test_full_half_mode_does_not_invent_generic_classification(self):
        result = self.calculate("FULL_HALF_MISTAKES")
        self.assertIn("not verified", result["qualification_note"])
        self.assertIsNone(result["qualification"])

    def test_unverified_profile_never_receives_qualification_claim(self):
        result = self.calculate(
            "ERROR_PERCENTAGE",
            error_allowance_percent=50,
            minimum_wpm=0,
            verification_status="UNVERIFIED",
        )
        self.assertIsNone(result["qualification"])
        self.assertIn("not verified", result["qualification_note"])

    def test_client_reported_keystrokes_are_explicitly_untrusted(self):
        result = calculate_result(
            reference="hello",
            typed="hello",
            duration_seconds=60,
            rules={"required_keystrokes": 5},
            reported_keystrokes=5,
        )
        self.assertEqual(result["reported_keystrokes"], 5)
        self.assertEqual(result["keystroke_count_source"], "client_reported")
        self.assertTrue(result["required_keystrokes_met"])
        self.assertIsNone(result["qualification"])

    def test_zero_duration_is_clamped_to_one_second(self):
        result = calculate_result(
            reference="a",
            typed="a",
            duration_seconds=0,
            rules={},
        )
        self.assertEqual(result["duration_seconds"], 1)
