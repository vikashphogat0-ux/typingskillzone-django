from django.test import SimpleTestCase

from .rulebook_scoring import evaluate_rulebook_scoring


class RulebookFormulaTests(SimpleTestCase):
    def test_weighted_net_wpm_uses_explicit_formula_and_parameters(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "NET_WPM_WEIGHTED_MISTAKES",
             "parameters": {"mistake_penalty_words": 1}},
            {"gross_words": 100, "weighted_mistakes": 5},
            duration_seconds=600,
        )
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual(result["metrics"]["net_words"], 95.0)
        self.assertEqual(result["metrics"]["net_wpm"], 9.5)

    def test_forgiveness_formula_applies_only_explicit_rate_and_penalty(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "NET_WPM_FORGIVENESS_EXCESS_PENALTY",
             "parameters": {"forgiveness_rate": 0.05, "excess_mistake_penalty_words": 10}},
            {"gross_words": 100, "weighted_mistakes": 8},
            duration_seconds=600,
        )
        self.assertEqual(result["metrics"]["forgiven_mistakes"], 5.0)
        self.assertEqual(result["metrics"]["excess_mistakes"], 3.0)
        self.assertEqual(result["metrics"]["net_words"], 70.0)

    def test_aiims_formula_requires_explicit_full_and_half_deductions(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "AIIMS_STROKE_DEDUCTION",
             "parameters": {"full_mistake_strokes": 50, "half_mistake_strokes": 25}},
            {"server_strokes": 1000, "full_mistakes": 2, "half_mistakes": 2},
            duration_seconds=600,
        )
        self.assertEqual(result["metrics"]["net_wpm"], 17.0)

    def test_full_half_categories_are_configured_not_assumed(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "ERROR_PERCENT_WEIGHTED",
             "parameters": {
                 "mistake_classification": {"full": ["omission"], "half": ["punctuation"]},
                 "full_mistake_weight": 1, "half_mistake_weight": 0.5,
             }},
            {"mistake_categories": {"omission": 2, "punctuation": 4}, "reference_words": 100},
            duration_seconds=600,
        )
        self.assertEqual(result["metrics"]["error_percent"], 4.0)

    def test_error_percent_supports_chsl_reference_word_denominator(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "ERROR_PERCENT_WEIGHTED",
             "parameters": {"denominator": "reference_words",
                            "full_mistake_weight": 1, "half_mistake_weight": 0.5}},
            {"weighted_mistakes": 20, "reference_words": 350, "typed_words": 300},
            duration_seconds=600,
        )
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual(result["metrics"]["error_percent"], 5.71)
        self.assertEqual(result["metrics"]["error_denominator"], 350.0)
        self.assertEqual(result["metrics"]["error_denominator_type"], "reference_words")

    def test_error_percent_supports_cgl_typed_word_denominator(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "ERROR_PERCENT_WEIGHTED",
             "parameters": {"denominator": "typed_words",
                            "full_mistake_weight": 1, "half_mistake_weight": 0.5}},
            {"weighted_mistakes": 30, "reference_words": 450, "typed_words": 400},
            duration_seconds=900,
        )
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual(result["metrics"]["error_percent"], 7.5)
        self.assertEqual(result["metrics"]["error_denominator"], 400.0)
        self.assertEqual(result["metrics"]["error_denominator_type"], "typed_words")

    def test_error_percent_rejects_missing_selected_denominator_metric(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "ERROR_PERCENT_WEIGHTED",
             "parameters": {"denominator": "typed_words"}},
            {"weighted_mistakes": 2, "reference_words": 100},
            duration_seconds=600,
        )
        self.assertEqual(result["evaluation_status"], "NOT_EVALUATED")
        self.assertEqual(result["metrics"], {})

    def test_marks_formula_and_speed_bands(self):
        marks = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "MARKS_PER_CORRECT_WORD",
             "parameters": {"marks_per_correct_word": 0.25, "maximum_marks": 25}},
            {"correct_words": 80}, duration_seconds=600,
        )
        self.assertEqual(marks["metrics"]["score"], 20.0)
        bands = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "SPEED_BANDS",
             "parameters": {"speed_metric": "net_wpm",
                            "bands": [{"minimum": 30, "marks": 10}, {"minimum": 40, "marks": 20}]}},
            {"net_wpm": 42}, duration_seconds=600,
        )
        self.assertEqual(bands["metrics"]["score"], 20.0)

    def test_missing_or_unsupported_formula_never_falls_back(self):
        result = evaluate_rulebook_scoring(
            {"formula": "GUESS_FROM_PROFILE"},
            {"gross_words": 100}, duration_seconds=600,
        )
        self.assertEqual(result["evaluation_status"], "NOT_EVALUATED")
        self.assertEqual(result["formula_status"], "NOT_EVALUATED")
        self.assertEqual(result["metrics"], {})


    def test_upsssc_exempts_first_five_wrong_words_then_applies_sixfold_penalty(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "UPSSSC_FIVE_EXEMPT_SIXFOLD",
             "parameters": {"exempt_wrong_words": 5, "penalty_multiplier": 6}},
            {"gross_words": 100, "wrong_words": 8}, duration_seconds=300,
        )
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual(result["metrics"]["chargeable_wrong_words"], 3.0)
        self.assertEqual(result["metrics"]["penalty_words"], 18.0)
        self.assertEqual(result["metrics"]["net_words"], 82.0)
        self.assertEqual(result["metrics"]["net_wpm"], 16.4)

    def test_spmcil_converts_weighted_mistakes_to_five_stroke_error_words(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "SPMCIL_STROKE_ERROR_WORDS",
             "parameters": {"strokes_per_word": 5}},
            {"server_strokes": 2000, "weighted_mistakes": 10}, duration_seconds=600,
        )
        self.assertEqual(result["metrics"]["gross_word_equivalents"], 400.0)
        self.assertEqual(result["metrics"]["error_words"], 2.0)
        self.assertEqual(result["metrics"]["net_wpm"], 39.8)

    def test_mp_cpct_requires_and_applies_explicit_net_speed_slabs(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "MP_CPCT_NET_WPM_SLABS",
             "parameters": {"words_per_error": 1, "bands": [
                 {"minimum_net_wpm": 30, "percentage": 50},
                 {"minimum_net_wpm": 41, "percentage": 60},
             ]}},
            {"gross_words": 600, "weighted_mistakes": 30}, duration_seconds=900,
        )
        self.assertEqual(result["metrics"]["net_wpm"], 38.0)
        self.assertEqual(result["metrics"]["score_percent"], 50.0)

    def test_mphc_marks_requires_server_measured_backspace_presses(self):
        config = {"engine_version": 1, "formula": "MPHC_MARKS_BACKSPACE_DEDUCTION",
                  "parameters": {"maximum_marks": 50, "wrong_word_deduction": 0.5,
                                 "backspace_deduction": 0.1}}
        unresolved = evaluate_rulebook_scoring(
            config, {"wrong_words": 10}, duration_seconds=600,
        )
        self.assertEqual(unresolved["evaluation_status"], "NOT_EVALUATED")
        result = evaluate_rulebook_scoring(
            config, {"wrong_words": 10, "backspace_presses": 20}, duration_seconds=600,
        )
        self.assertEqual(result["metrics"]["score"], 43.0)


    def test_aiims_marks_insufficient_attempt_below_language_stroke_floor(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "AIIMS_STROKE_DEDUCTION",
             "parameters": {"minimum_strokes": 2625, "penalty_strokes_per_mistake": 50}},
            {"server_strokes": 2500, "weighted_mistakes": 2}, duration_seconds=900,
        )
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual(result["metrics"]["attempt_status"], "INSUFFICIENT_ATTEMPT")
        self.assertIsNone(result["metrics"]["net_wpm"])

    def test_aiims_applies_fifty_stroke_penalty_after_minimum_attempt(self):
        result = evaluate_rulebook_scoring(
            {"engine_version": 1, "formula": "AIIMS_STROKE_DEDUCTION",
             "parameters": {"minimum_strokes": 2625, "penalty_strokes_per_mistake": 50}},
            {"server_strokes": 3000, "weighted_mistakes": 2}, duration_seconds=900,
        )
        self.assertEqual(result["metrics"]["attempt_status"], "SUFFICIENT_ATTEMPT")
        self.assertEqual(result["metrics"]["net_wpm"], 39.33)
        self.assertEqual(result["metrics"]["accuracy_percent"], 98.33)


class RulebookFormulaIntegrationTests(SimpleTestCase):
    def test_internal_profile_uses_versioned_formula_for_score_and_speed(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta gamma delta",
            typed="alpha beta gamma delta",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "scoring_mode": "GENERIC",
                "scoring_rules": {
                    "rulebook_verification": "internal",
                    "rulebook_scoring": {
                        "engine_version": 1,
                        "formula": "CORRECT_WORDS_PER_MINUTE",
                        "parameters": {},
                    },
                },
                "qualification_rules": {},
            },
        )
        self.assertEqual(result["formula_evaluation_status"], "EVALUATED")
        self.assertEqual(result["formula_id"], "CORRECT_WORDS_PER_MINUTE")
        self.assertEqual(result["net_wpm"], 4.0)
        self.assertIsNone(result["score"])

    def test_internal_profile_without_formula_does_not_publish_legacy_score(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta gamma delta",
            typed="alpha beta gamma delta",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "scoring_mode": "CORRECT_WORD_MARKS",
                "scoring_rules": {
                    "rulebook_verification": "internal",
                    "marks_per_correct_word": 5,
                },
                "qualification_rules": {},
            },
        )
        self.assertEqual(result["formula_evaluation_status"], "NOT_EVALUATED")
        self.assertIsNone(result["score"])
        self.assertIsNone(result["net_wpm"])
