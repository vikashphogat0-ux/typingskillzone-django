from django.test import SimpleTestCase

from typing_sessions.scoring import calculate_result


class SSCCHSL2025ScoringTests(SimpleTestCase):
    def _vh_result(self, strokes):
        reference = "a" * strokes
        return calculate_result(
            reference=reference,
            typed=reference,
            duration_seconds=900,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "scoring_rules": {
                    "formula": "SSC_CHSL_2025_VH_ENGLISH",
                    "minimum_wpm": 35,
                    "minimum_kdph": 10500,
                    "category_error_caps": {"PWD": 10},
                },
            },
        )

    def test_vh_15_minute_compensatory_attempt_uses_15_minute_denominator(self):
        result = self._vh_result(2625)
        self.assertEqual(result["gross_wpm"], 35)
        self.assertEqual(result["gross_kdph"], 10500)
        self.assertEqual(result["required_keystrokes"], 2625)
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_vh_attempt_below_speed_after_compensatory_time_does_not_qualify(self):
        result = self._vh_result(2600)
        self.assertEqual(result["gross_wpm"], 34.67)
        self.assertFalse(result["qualification"])
        self.assertEqual(result["qualification_status"], "NOT_QUALIFIED")

    def test_standard_chsl_english_uses_cycle_specific_category_error_caps(self):
        reference = "word " * 350
        result = calculate_result(
            reference=reference,
            typed=reference,
            duration_seconds=600,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "candidate_category": "UR",
                "scoring_rules": {
                    "formula": "SSC_CHSL_2025_ENGLISH",
                    "minimum_wpm": 35,
                    "minimum_kdph": 10500,
                    "category_error_caps": {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
                },
            },
        )
        self.assertEqual(result["gross_wpm"], 35)
        self.assertEqual(result["gross_kdph"], 10500)
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "QUALIFIED")
        self.assertIsNone(result["score"])
