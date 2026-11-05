from django.test import SimpleTestCase

from typing_sessions.dphcm_error_analysis import analyze_dphcm_text_errors


class DelhiPoliceHCMErrorAnalysisTests(SimpleTestCase):
    def test_exact_text_has_no_candidate_errors(self):
        result = analyze_dphcm_text_errors(reference="The quick fox.", typed="The quick fox.")
        self.assertEqual(result["status"], "ANALYZED")
        self.assertEqual(result["candidate_error_count"], 0)
        self.assertIsNone(result["official_mistake_count"])

    def test_omitted_reference_word_is_reported(self):
        result = analyze_dphcm_text_errors(reference="The quick brown fox", typed="The brown fox")
        self.assertIn("OMISSION", [item["category"] for item in result["candidate_errors"]])

    def test_substitution_is_reported(self):
        result = analyze_dphcm_text_errors(reference="The quick fox", typed="The quiet fox")
        self.assertIn("SUBSTITUTION", [item["category"] for item in result["candidate_errors"]])

    def test_capitalization_is_reported(self):
        result = analyze_dphcm_text_errors(reference="Delhi Police", typed="delhi Police")
        self.assertIn("CAPITALIZATION", [item["category"] for item in result["candidate_errors"]])

    def test_punctuation_addition_is_reported(self):
        result = analyze_dphcm_text_errors(reference="Hello world", typed="Hello, world")
        self.assertIn("ADDITION_OF_PUNCTUATION", [item["category"] for item in result["candidate_errors"]])

    def test_internal_word_gap_is_reported(self):
        result = analyze_dphcm_text_errors(reference="typing", typed="typ ing")
        self.assertIn("GAP_INSIDE_WORD", [item["category"] for item in result["candidate_errors"]])

    def test_missing_paragraph_is_reported(self):
        result = analyze_dphcm_text_errors(reference="First paragraph\n\nSecond paragraph", typed="First paragraph")
        self.assertIn("MISSING_PARAGRAPH", [item["category"] for item in result["candidate_errors"]])

    def test_added_word_is_unresolved_not_guessed_as_official_category(self):
        result = analyze_dphcm_text_errors(reference="The fox", typed="The quick fox")
        self.assertTrue(result["unresolved_cases"])
        self.assertIsNone(result["official_mistake_count"])

    def test_invalid_text_is_rejected(self):
        result = analyze_dphcm_text_errors(reference=None, typed="text")
        self.assertEqual(result["status"], "INVALID_TEXT")
        self.assertFalse(result["official_scoring_eligible"])

    def test_excess_gap_between_words_is_reported(self):
        result = analyze_dphcm_text_errors(reference="two words", typed="two  words")
        self.assertIn("EXCESS_GAP_BETWEEN_WORDS", [item["category"] for item in result["candidate_errors"]])
