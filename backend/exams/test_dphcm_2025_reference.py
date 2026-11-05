from django.test import SimpleTestCase

from exams.reference_profiles.delhi_police_hcm_2025 import (
    OFFICIAL_RULES,
    evaluate_dphcm_2025,
)


class DelhiPoliceHCM2025ReferenceProfileTests(SimpleTestCase):
    def test_english_minimum_speed_awards_ten_marks(self):
        result = evaluate_dphcm_2025(
            language="ENGLISH", total_strokes=1500, mistake_count=0
        )
        self.assertEqual(result["status"], "SCORED")
        self.assertEqual(result["actual_speed_wpm"], 30)
        self.assertEqual(result["score"], 10)

    def test_hindi_minimum_speed_awards_ten_marks(self):
        result = evaluate_dphcm_2025(
            language="HINDI", total_strokes=1250, mistake_count=0
        )
        self.assertEqual(result["status"], "SCORED")
        self.assertEqual(result["actual_speed_wpm"], 25)
        self.assertEqual(result["score"], 10)

    def test_one_mistake_reduces_actual_speed_by_one_word_per_minute(self):
        result = evaluate_dphcm_2025(
            language="ENGLISH", total_strokes=2000, mistake_count=10
        )
        self.assertEqual(result["tentative_speed_wpm"], 40)
        self.assertEqual(result["actual_speed_wpm"], 30)
        self.assertEqual(result["score"], 10)

    def test_english_marks_bands(self):
        cases = [(1550, 0, 31, 12), (1800, 0, 36, 15),
                 (2050, 0, 41, 18), (2300, 0, 46, 21),
                 (2550, 0, 51, 25)]
        for strokes, mistakes, speed, marks in cases:
            with self.subTest(speed=speed):
                result = evaluate_dphcm_2025(
                    language="ENGLISH", total_strokes=strokes, mistake_count=mistakes
                )
                self.assertEqual(result["actual_speed_wpm"], speed)
                self.assertEqual(result["score"], marks)

    def test_hindi_marks_bands(self):
        cases = [(1300, 0, 26, 12), (1550, 0, 31, 15),
                 (1800, 0, 36, 18), (2050, 0, 41, 21),
                 (2300, 0, 46, 25)]
        for strokes, mistakes, speed, marks in cases:
            with self.subTest(speed=speed):
                result = evaluate_dphcm_2025(
                    language="HINDI", total_strokes=strokes, mistake_count=mistakes
                )
                self.assertEqual(result["actual_speed_wpm"], speed)
                self.assertEqual(result["score"], marks)

    def test_below_minimum_is_disqualified(self):
        result = evaluate_dphcm_2025(
            language="ENGLISH", total_strokes=1450, mistake_count=1
        )
        self.assertEqual(result["status"], "DISQUALIFIED")
        self.assertEqual(result["score"], 0)

    def test_fractional_speed_is_not_rounded_without_official_rule(self):
        result = evaluate_dphcm_2025(
            language="ENGLISH", total_strokes=1525, mistake_count=0
        )
        self.assertEqual(result["actual_speed_wpm"], 30.5)
        self.assertEqual(result["status"], "BAND_UNRESOLVED")
        self.assertIsNone(result["score"])

    def test_invalid_inputs_and_unverified_hindi_keystroke_count_are_not_guessed(self):
        result = evaluate_dphcm_2025(
            language="HINDI", total_strokes="1250", mistake_count=0
        )
        self.assertEqual(result["status"], "INVALID_STROKE_COUNT")
        self.assertEqual(
            OFFICIAL_RULES["speed_formula"]["stroke_count_source"],
            "MUST_BE_MEASURED_OR_SUPPLIED_BY_A_VERIFIED_STROKE_COUNTER",
        )

    def test_backspace_restriction_is_not_invented(self):
        self.assertEqual(OFFICIAL_RULES["input_restrictions"]["backspace"], "NOT_SPECIFIED")
