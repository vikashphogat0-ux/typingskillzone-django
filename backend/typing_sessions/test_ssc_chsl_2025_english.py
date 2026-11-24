from django.test import SimpleTestCase

from .scoring import calculate_result


def chsl_rules(category="UR"):
    return {
        "exam_code": "ssc-chsl-2025-english-test-tcs-interface",
        "scoring_mode": "CUSTOM",
        "verification_status": "PARTIAL",
        "minimum_wpm": 35,
        "required_keystrokes": 1750,
        "strokes_per_word": 5,
        "candidate_category": category,
        "error_rules": {},
        "scoring_rules": {
            "formula": "SSC_CHSL_2025_ENGLISH",
            "minimum_wpm": 35,
            "minimum_kdph": 10500,
            "minimum_strokes": 1750,
            "category_error_caps": {
                "UR": 7, "OBC": 10, "EWS": 10, "SC": 10,
                "ST": 10, "PWD": 10, "OTHER_RESERVED": 10,
            },
            "candidate_category_default": "UR",
        },
        "qualification_rules": {},
    }


class SSCCHSL2025EnglishScoringTests(SimpleTestCase):
    def setUp(self):
        self.words = [f"word{i}" for i in range(350)]
        self.reference = " ".join(self.words)

    def test_35_wpm_and_10500_kdph_from_1750_strokes(self):
        result = calculate_result(
            reference=self.reference,
            typed=self.reference,
            duration_seconds=600,
            reported_keystrokes=1750,
            rules=chsl_rules(),
        )
        self.assertEqual(result["gross_wpm"], 35)
        self.assertEqual(result["gross_kdph"], 10500)
        self.assertEqual(result["reference_word_count"], 350)
        self.assertEqual(result["error_percent"], 0)
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "PROVISIONAL_QUALIFIED")


    def test_fifteen_minute_compensatory_attempt_scales_target_to_2625_strokes(self):
        result = calculate_result(
            reference=self.reference,
            typed=self.reference,
            duration_seconds=900,
            reported_keystrokes=2625,
            rules=chsl_rules(),
        )
        self.assertEqual(result["gross_wpm"], 35)
        self.assertEqual(result["gross_kdph"], 10500)
        self.assertEqual(result["required_keystrokes"], 2625)
        self.assertTrue(result["required_keystrokes_met"])
        self.assertTrue(result["qualification"])

    def test_error_percent_uses_total_reference_passage_words(self):
        typed_words = list(self.words)
        typed_words[:25] = [f"wrong{i}" for i in range(25)]
        result = calculate_result(
            reference=self.reference,
            typed=" ".join(typed_words),
            duration_seconds=600,
            reported_keystrokes=1750,
            rules=chsl_rules("UR"),
        )
        self.assertEqual(result["full_mistakes"], 25)
        self.assertEqual(result["half_mistakes"], 0)
        self.assertEqual(result["reference_word_count"], 350)
        self.assertEqual(result["error_percent"], 7.14)
        self.assertFalse(result["qualification"])

    def test_reserved_category_uses_ten_percent_error_cap(self):
        typed_words = list(self.words)
        typed_words[:25] = [f"wrong{i}" for i in range(25)]
        result = calculate_result(
            reference=self.reference,
            typed=" ".join(typed_words),
            duration_seconds=600,
            reported_keystrokes=1750,
            rules=chsl_rules("SC"),
        )
        self.assertEqual(result["category_error_cap"], 10)
        self.assertTrue(result["qualification"])

    def test_half_mistake_counts_as_half_error(self):
        reference = "alpha beta gamma delta"
        typed = "alpha beta, gamma delta"
        result = calculate_result(
            reference=reference,
            typed=typed,
            duration_seconds=600,
            reported_keystrokes=1750,
            rules=chsl_rules(),
        )
        self.assertEqual(result["full_mistakes"], 0)
        self.assertEqual(result["half_mistakes"], 1)
        self.assertEqual(result["error_count"], 0.5)
        self.assertEqual(result["error_percent"], 12.5)

    def test_speed_below_35_wpm_fails_even_with_zero_errors(self):
        result = calculate_result(
            reference=self.reference,
            typed=self.reference,
            duration_seconds=600,
            reported_keystrokes=1749,
            rules=chsl_rules(),
        )
        self.assertLess(result["gross_wpm"], 35)
        self.assertFalse(result["qualification"])
        self.assertFalse(result["speed_requirement_met"])
