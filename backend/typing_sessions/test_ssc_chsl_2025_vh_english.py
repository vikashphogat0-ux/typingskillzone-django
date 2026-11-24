from django.test import SimpleTestCase

from .scoring import calculate_result


class SSCCHSL2025VHEnglishScoringTests(SimpleTestCase):
    def setUp(self):
        # 400 words, exactly 2,625 submitted characters including spaces.
        short_words = ["abcde"] * 174 + ["abcdef"] * 226
        self.reference = " ".join(short_words)
        self.assertEqual(len(self.reference), 2625)
        self.rules = {
            "scoring_mode": "CUSTOM",
            "verification_status": "VERIFIED",
            "minimum_wpm": 35,
            "required_keystrokes": 2625,
            "strokes_per_word": 5,
            "error_allowance_percent": 10,
            "error_rules": {},
            "scoring_rules": {
                "formula": "SSC_CHSL_2025_VH_ENGLISH",
                "profile_variant": "VH_CATEGORY_ENGLISH",
                "minimum_wpm": 35,
                "minimum_kdph": 10500,
                "minimum_strokes": 2625,
                "scoring_duration_seconds": 900,
                "category_error_caps": {"PWD": 10},
            },
            "qualification_rules": {
                "mode": "QUALIFYING_ONLY",
                "minimum_wpm": 35,
                "maximum_error_percent": 10,
                "all": [
                    {"metric": "gross_wpm", "operator": "gte", "value": 35},
                    {"metric": "error_percent", "operator": "lte", "value": 10},
                ],
            },
        }

    def test_fifteen_minute_attempt_uses_ten_minute_speed_scoring_base(self):
        result = calculate_result(
            reference=self.reference,
            typed=self.reference,
            duration_seconds=900,
            reported_keystrokes=999999,  # untrusted telemetry is ignored for verified profiles
            rules=self.rules,
        )
        self.assertEqual(result["duration_seconds"], 900)
        self.assertEqual(result["gross_wpm"], 35)
        self.assertEqual(result["gross_kdph"], 10500)
        self.assertEqual(result["error_percent"], 0)
        self.assertEqual(result["qualification_status"], "QUALIFIED")
        self.assertTrue(result["qualification"])
        self.assertEqual(result["stroke_count_for_speed"], 1750)
        self.assertEqual(result["stroke_count_source"], "server_derived")
