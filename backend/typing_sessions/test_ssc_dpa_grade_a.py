from django.test import SimpleTestCase

from .scoring import calculate_result, _classify_dpa_mistakes


def dpa_rules(category="UR"):
    return {
        "exam_code": "ssc-data-processing-assistant-grade-a",
        "scoring_mode": "CUSTOM",
        "verification_status": "PARTIAL",
        "required_keystrokes": 3750,
        "strokes_per_word": 5,
        "candidate_category": category,
        "error_rules": {},
        "scoring_rules": {
            "formula": "SSC_DPA_GRADE_A",
            "minimum_strokes": 3750,
            "strokes_per_word": 5,
            "candidate_category_default": "UR",
            "category_error_caps": {
                "UR": 5, "OBC": 7, "EWS": 7, "SC": 10,
                "ST": 10, "PWD": 10, "OTHER_RESERVED": 10,
            },
        },
        "qualification_rules": {"allow_partial_verification": True},
    }


class SSCDataProcessingAssistantGradeATests(SimpleTestCase):
    def test_exact_3750_strokes_meets_15000_kdph_and_50_gwpm(self):
        words = [f"word{i}" for i in range(750)]
        passage = " ".join(words)
        result = calculate_result(
            reference=passage,
            typed=passage,
            duration_seconds=900,
            reported_keystrokes=3750,
            rules=dpa_rules(),
        )
        self.assertEqual(result["gross_kdph"], 15000)
        self.assertEqual(result["gross_wpm"], 50)
        self.assertEqual(result["net_wpm"], 50)
        self.assertEqual(result["error_percent"], 0)
        self.assertTrue(result["required_keystrokes_met"])
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "PROVISIONAL_QUALIFIED")
        self.assertIsNone(result["score"])


    def test_compensatory_duration_scales_the_15000_kdph_stroke_floor(self):
        words = [f"word{i}" for i in range(1000)]
        passage = " ".join(words)
        result = calculate_result(
            reference=passage,
            typed=passage,
            duration_seconds=1200,
            reported_keystrokes=5000,
            rules=dpa_rules(),
        )
        self.assertEqual(result["gross_kdph"], 15000)
        self.assertEqual(result["required_keystrokes"], 5000)
        self.assertTrue(result["required_keystrokes_met"])
        self.assertEqual(result["gross_wpm"], 50)

    def test_category_specific_error_ceiling_is_applied(self):
        reference_words = [f"word{i}" for i in range(750)]
        typed_words = [f"wrong{i}" for i in range(40)] + reference_words[40:]
        result_ur = calculate_result(
            reference=" ".join(reference_words),
            typed=" ".join(typed_words),
            duration_seconds=900,
            reported_keystrokes=3750,
            rules=dpa_rules("UR"),
        )
        result_obc = calculate_result(
            reference=" ".join(reference_words),
            typed=" ".join(typed_words),
            duration_seconds=900,
            reported_keystrokes=3750,
            rules=dpa_rules("OBC"),
        )
        self.assertGreater(result_ur["error_percent"], 5)
        self.assertFalse(result_ur["qualification"])
        self.assertEqual(result_ur["qualification_status"], "PROVISIONAL_NOT_QUALIFIED")
        self.assertLessEqual(result_obc["error_percent"], 7)
        self.assertTrue(result_obc["qualification"])

    def test_punctuation_is_one_half_mistake(self):
        analysis = _classify_dpa_mistakes("alpha beta gamma", "alpha beta, gamma")
        categories = analysis["categories"]
        self.assertEqual(categories["punctuation"], 1)
        result = calculate_result(
            reference="alpha beta gamma",
            typed="alpha beta, gamma",
            duration_seconds=900,
            reported_keystrokes=3750,
            rules=dpa_rules(),
        )
        self.assertEqual(result["full_mistakes"], 0)
        self.assertEqual(result["half_mistakes"], 1)
        self.assertEqual(result["error_count"], 0.5)

    def test_adjacent_word_transposition_is_one_half_mistake(self):
        analysis = _classify_dpa_mistakes("one two three four", "two one three four")
        self.assertEqual(analysis["categories"]["transposition"], 1)
        result = calculate_result(
            reference="one two three four",
            typed="two one three four",
            duration_seconds=900,
            reported_keystrokes=3750,
            rules=dpa_rules(),
        )
        self.assertEqual(result["full_mistakes"], 0)
        self.assertEqual(result["half_mistakes"], 1)
        self.assertEqual(result["error_count"], 0.5)

    def test_spaces_instead_of_tab_are_one_half_mistake_per_paragraph(self):
        analysis = _classify_dpa_mistakes(
            "\tFirst paragraph\n\n\tSecond paragraph",
            "  First paragraph\n\n  Second paragraph",
        )
        self.assertEqual(analysis["categories"]["paragraph_indentation"], 2)
        self.assertEqual(analysis["total_detected_errors"], 2)
