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

    def test_adjacent_word_transposition_is_a_half_mistake(self):
        reference = "I hope " + ("word " * 350)
        typed = "hope I " + ("word " * 350)
        result = calculate_result(
            reference=reference,
            typed=typed,
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
        self.assertEqual(result["mistake_categories"]["transposition"], 1)
        self.assertEqual(result["half_mistakes"], 1)
        self.assertEqual(result["weighted_mistakes"], 0.5)

    def test_chsl_2025_cycle_cutoff_uses_seven_percent_ur_and_ten_percent_reserved(self):
        reference = "word " * 350
        typed = ("wrong " * 25) + ("word " * 325)

        def score(category):
            return calculate_result(
                reference=reference,
                typed=typed,
                duration_seconds=600,
                rules={
                    "scoring_mode": "CUSTOM",
                    "verification_status": "VERIFIED",
                    "candidate_category": category,
                    "scoring_rules": {
                        "formula": "SSC_CHSL_2025_ENGLISH",
                        "minimum_wpm": 35,
                        "minimum_kdph": 10500,
                        "category_error_caps": {
                            "UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10,
                            "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10,
                        },
                    },
                },
            )

        ur = score("UR")
        reserved = score("OBC")
        self.assertEqual(ur["error_percent"], 7.14)
        self.assertFalse(ur["qualification"])
        self.assertEqual(reserved["error_percent"], 7.14)
        self.assertTrue(reserved["qualification"])

    def test_chsl_hindi_uses_30_wpm_9000_kdph_and_no_capitalization_half_errors(self):
        reference = "राम " * 375
        result = calculate_result(
            reference=reference,
            typed=reference,
            duration_seconds=600,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "candidate_category": "UR",
                "scoring_rules": {
                    "formula": "SSC_CHSL_2025_HINDI_MANGAL",
                    "minimum_wpm": 30,
                    "minimum_kdph": 9000,
                    "category_error_caps": {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
                },
            },
        )
        self.assertEqual(result["gross_wpm"], 30)
        self.assertEqual(result["gross_kdph"], 9000)
        self.assertEqual(result["required_keystrokes"], 1500)
        self.assertEqual(result["half_mistakes"], 0)
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_chsl_hindi_uses_category_error_cutoff(self):
        reference = "राम " * 375
        typed = ("श्याम " * 30) + ("राम " * 345)
        result = calculate_result(
            reference=reference,
            typed=typed,
            duration_seconds=600,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "candidate_category": "UR",
                "scoring_rules": {
                    "formula": "SSC_CHSL_2025_HINDI_KRUTIDEV",
                    "minimum_wpm": 30,
                    "minimum_kdph": 9000,
                    "category_error_caps": {"UR": 7, "OBC": 10},
                },
            },
        )
        self.assertFalse(result["qualification"])
        self.assertEqual(result["qualification_status"], "NOT_QUALIFIED")

class SSCCGL2025DESTScoringTests(SimpleTestCase):
    def _result(self, standard):
        reference = "alpha " * 100
        typed = ("bravo " * 10) + ("alpha " * 90)
        return calculate_result(
            reference=reference,
            typed=typed,
            duration_seconds=900,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "candidate_category": "UR",
                "scoring_rules": {
                    "formula": "SSC_CGL_2025_DEST",
                    "standard_type": standard,
                    "normal_error_caps": {"UR": 20, "OBC": 25, "EWS": 25, "SC": 30, "ST": 30, "ESM": 30, "OH": 30, "HH": 30, "VH": 30, "PWD": 30},
                    "higher_error_caps": {"UR": 5, "OBC": 7, "EWS": 7, "SC": 7, "ST": 7, "ESM": 7, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
                },
            },
        )

    def test_cgl_normal_ur_standard_uses_20_percent_error_ceiling(self):
        result = self._result("NORMAL")
        self.assertEqual(result["error_percent"], 10)
        self.assertEqual(result["category_error_cap"], 20)
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_cgl_higher_ur_standard_uses_5_percent_error_ceiling(self):
        result = self._result("HIGHER")
        self.assertEqual(result["error_percent"], 10)
        self.assertEqual(result["category_error_cap"], 5)
        self.assertFalse(result["qualification"])
        self.assertEqual(result["qualification_status"], "NOT_QUALIFIED")

    def test_cgl_2000_passage_size_is_not_a_candidate_minimum(self):
        result = calculate_result(
            reference="alpha " * 100,
            typed="alpha " * 100,
            duration_seconds=900,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "candidate_category": "UR",
                "scoring_rules": {
                    "formula": "SSC_CGL_2025_DEST",
                    "standard_type": "NORMAL",
                    "normal_error_caps": {"UR": 20},
                },
            },
        )
        self.assertIsNone(result["required_keystrokes"])
        self.assertTrue(result["qualification"])
