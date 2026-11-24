from django.test import SimpleTestCase

from typing_sessions.scoring import calculate_result


class DelhiPoliceHCM2025ScoringTests(SimpleTestCase):
    def _result(self, *, words, minimum_wpm=30, language="ENGLISH", mistakes=0):
        # A controlled passage makes each detected mismatch deterministic.
        reference_words = [f"word{i}" for i in range(words)]
        typed_words = list(reference_words)
        for index in range(mistakes):
            typed_words[index] = f"wrong{index}"
        reference = " ".join(reference_words)
        typed = " ".join(typed_words)
        return calculate_result(
            reference=reference,
            typed=typed,
            duration_seconds=600,
            rules={
                "scoring_mode": "CUSTOM",
                "verification_status": "VERIFIED",
                "language": language,
                "scoring_rules": {
                    "formula": "DELHI_POLICE_HCM_2025",
                    "minimum_wpm": minimum_wpm,
                },
            },
        )

    def test_english_minimum_speed_gets_ten_marks(self):
        result = self._result(words=300)
        self.assertEqual(result["gross_wpm"], 30)
        self.assertEqual(result["net_wpm"], 30)
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_english_below_minimum_is_disqualified_and_gets_zero(self):
        result = self._result(words=290)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["qualification_status"], "DISQUALIFIED")

    def test_one_mistake_deducts_one_word_from_speed(self):
        result = self._result(words=310, mistakes=1)
        self.assertEqual(result["gross_wpm"], 31)
        self.assertEqual(result["net_wpm"], 30.9)
        self.assertEqual(result["full_mistakes"], 1)
        self.assertEqual(result["half_mistakes"], 0)
        self.assertEqual(result["score"], 10)

    def test_english_marks_slabs(self):
        expected = [(310, 12), (360, 15), (410, 18), (460, 21), (510, 25)]
        for words, marks in expected:
            with self.subTest(words=words):
                self.assertEqual(self._result(words=words)["score"], marks)

    def test_hindi_uses_its_own_minimum_and_marks_slabs(self):
        result = self._result(words=250, minimum_wpm=25, language="HINDI")
        self.assertEqual(result["net_wpm"], 25)
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["qualification_status"], "QUALIFIED")
