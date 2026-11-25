from django.test import SimpleTestCase

from .rulebook_evaluation import evaluate_rulebook_qualification


class RulebookEvaluationTests(SimpleTestCase):
    def test_all_criteria_qualify_and_return_audit_rows(self):
        result = evaluate_rulebook_qualification(
            {
                "engine_version": 1,
                "mode": "ALL",
                "criteria": [
                    {"id": "speed", "label": "Minimum speed", "metric": "net_wpm", "operator": "gte", "value": 35},
                    {"id": "errors", "label": "Maximum errors", "metric": "error_percent", "operator": "lte", "value": 7},
                ],
            },
            {"net_wpm": 38, "error_percent": 5.5},
        )
        self.assertEqual(result["qualification_status"], "QUALIFIED")
        self.assertEqual(result["evaluation_status"], "EVALUATED")
        self.assertEqual([row["status"] for row in result["qualification_checks"]], ["MET", "MET"])

    def test_failed_criterion_disqualifies_all_mode(self):
        result = evaluate_rulebook_qualification(
            {"engine_version": 1, "mode": "ALL", "criteria": [
                {"metric": "net_wpm", "operator": "gte", "value": 35},
                {"metric": "error_percent", "operator": "lte", "value": 7},
            ]},
            {"net_wpm": 34.99, "error_percent": 4},
        )
        self.assertEqual(result["qualification_status"], "NOT QUALIFIED")
        self.assertFalse(result["qualification"])

    def test_any_mode_uses_any_criterion(self):
        result = evaluate_rulebook_qualification(
            {"engine_version": 1, "mode": "ANY", "criteria": [
                {"metric": "net_wpm", "operator": "gte", "value": 40},
                {"metric": "score", "operator": "gte", "value": 10},
            ]},
            {"net_wpm": 35, "score": 12},
        )
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_category_specific_limit_requires_selected_category(self):
        config = {"engine_version": 1, "mode": "ALL", "criteria": [
            {"label": "Category error ceiling", "metric": "error_percent", "operator": "lte",
             "category_values": {"UR": 7, "SC": 10}}
        ]}
        missing = evaluate_rulebook_qualification(config, {"error_percent": 8})
        self.assertEqual(missing["qualification_status"], "NOT EVALUATED")
        selected = evaluate_rulebook_qualification(config, {"error_percent": 8}, candidate_category="SC")
        self.assertEqual(selected["qualification_status"], "QUALIFIED")

    def test_selector_condition_skips_higher_threshold_for_normal_and_applies_it_for_higher(self):
        config = {"engine_version": 1, "mode": "ALL", "criteria": [
            {"id": "normal", "metric": "error_percent", "operator": "lte", "category_values": {"UR": 20}},
            {"id": "higher", "metric": "error_percent", "operator": "lte",
             "category_values": {"UR": 5}, "when_selectors": {"standard_type": "HIGHER"}},
        ]}
        normal = evaluate_rulebook_qualification(config, {"error_percent": 10}, candidate_category="UR",
            selectors={"standard_type": "NORMAL"})
        self.assertEqual(normal["qualification_status"], "QUALIFIED")
        self.assertEqual(normal["qualification_checks"][1]["status"], "NOT APPLICABLE")
        higher = evaluate_rulebook_qualification(config, {"error_percent": 10}, candidate_category="UR",
            selectors={"standard_type": "HIGHER"})
        self.assertEqual(higher["qualification_status"], "NOT QUALIFIED")

    def test_selector_threshold_mapping_requires_a_saved_choice(self):
        config = {"engine_version": 1, "mode": "ALL", "criteria": [
            {"metric": "net_wpm", "operator": "gte", "selector": "variant_id",
             "selector_values": {"normal": 30, "higher": 40}}
        ]}
        missing = evaluate_rulebook_qualification(config, {"net_wpm": 35}, selectors={})
        self.assertEqual(missing["qualification_status"], "NOT EVALUATED")
        selected = evaluate_rulebook_qualification(config, {"net_wpm": 35}, selectors={"variant_id": "normal"})
        self.assertEqual(selected["qualification_status"], "QUALIFIED")

    def test_unsupported_or_missing_metric_never_becomes_a_fail_or_pass(self):
        result = evaluate_rulebook_qualification(
            {"engine_version": 1, "criteria": [
                {"metric": "unknown_metric", "operator": "gte", "value": 10}
            ]},
            {},
        )
        self.assertEqual(result["evaluation_status"], "NOT_EVALUATED")
        self.assertIsNone(result["qualification"])

    def test_unversioned_legacy_criteria_are_not_executed(self):
        result = evaluate_rulebook_qualification(
            {"all": [{"metric": "net_wpm", "operator": "gte", "value": 1}]},
            {"net_wpm": 100},
        )
        self.assertEqual(result["qualification_status"], "NOT EVALUATED")
        self.assertIsNone(result["qualification"])

    def test_malformed_values_and_boolean_thresholds_are_rejected(self):
        result = evaluate_rulebook_qualification(
            {"engine_version": 1, "criteria": [
                {"metric": "net_wpm", "operator": "gte", "value": True}
            ]},
            {"net_wpm": 50},
        )
        self.assertEqual(result["qualification_status"], "NOT EVALUATED")


class RulebookScoringIntegrationTests(SimpleTestCase):
    def test_internal_rulebook_profile_ignores_legacy_minimum_speed_fallback(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta gamma delta",
            typed="alpha beta gamma delta",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "minimum_wpm": 999,
                "scoring_mode": "GENERIC",
                "scoring_rules": {"rulebook_verification": "internal"},
                "qualification_rules": {},
            },
        )
        self.assertEqual(result["qualification_status"], "NOT EVALUATED")
        self.assertIsNone(result["qualification"])
        self.assertEqual(result["evaluation_status"], "NOT_EVALUATED")

    def test_internal_rulebook_profile_uses_only_versioned_structured_criteria(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta gamma delta",
            typed="alpha beta gamma delta",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "minimum_wpm": 999,
                "scoring_mode": "GENERIC",
                "scoring_rules": {"rulebook_verification": "internal"},
                "qualification_rules": {
                    "engine_version": 1,
                    "mode": "ALL",
                    "criteria": [
                        {"metric": "gross_wpm", "operator": "gte", "value": 4}
                    ],
                },
            },
        )
        self.assertEqual(result["qualification_status"], "QUALIFIED")
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_checks"][0]["status"], "MET")
