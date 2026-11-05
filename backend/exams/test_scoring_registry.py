from django.test import SimpleTestCase

from .scoring_registry import resolve_scoring_specification


class ScoringSpecificationRegistryTests(SimpleTestCase):
    def test_generic_metrics_are_explicitly_practice_only(self):
        result = resolve_scoring_specification({"scoring_mode": "GENERIC"})
        self.assertEqual(result["formula_id"], "PRACTICE_CHARACTER_METRICS")
        self.assertEqual(result["status"], "PRACTICE_ONLY")
        self.assertFalse(result["qualification_eligible"])

    def test_error_percentage_requires_word_unit_and_explicit_allowance(self):
        incomplete = resolve_scoring_specification({
            "scoring_mode": "ERROR_PERCENTAGE",
            "error_allowance_percent": "10",
            "error_rules": {"count_word_errors": False},
        })
        self.assertEqual(incomplete["status"], "PARTIAL")
        self.assertFalse(incomplete["qualification_eligible"])
        self.assertIn("error_rules.count_word_errors", [item["field"] for item in incomplete["unresolved"]])

    def test_verified_word_error_formula_is_qualification_eligible(self):
        result = resolve_scoring_specification({
            "scoring_mode": "ERROR_PERCENTAGE",
            "error_allowance_percent": "10",
            "error_rules": {"count_word_errors": True},
            "verification_status": "VERIFIED",
        })
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["qualification_eligible"])
        self.assertEqual(result["parameters"]["error_unit"], "word")

    def test_domain_evidence_requires_both_scoring_and_qualification_verification(self):
        rules = {
            "scoring_mode": "ERROR_PERCENTAGE",
            "error_allowance_percent": "10",
            "error_rules": {"count_word_errors": True},
            "verification_status": "VERIFIED",
            "domain_evidence_snapshot": {
                "domains": {
                    "scoring": {"status": "VERIFIED"},
                    "qualification": {"status": "UNVERIFIED"},
                },
            },
        }
        result = resolve_scoring_specification(rules)
        self.assertEqual(result["status"], "READY")
        self.assertFalse(result["qualification_eligible"])
        self.assertEqual(result["provenance"]["qualification"], "UNVERIFIED")

    def test_stroke_penalty_requires_explicit_units_and_penalty(self):
        result = resolve_scoring_specification({
            "scoring_mode": "STROKE_PENALTY",
            "strokes_per_word": 5,
            "mistake_penalty_strokes": 5,
            "error_rules": {},
        })
        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["qualification_eligible"])

    def test_unknown_mode_is_not_executed_as_a_registered_formula(self):
        result = resolve_scoring_specification({"scoring_mode": "FUTURE_MODE"})
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIsNone(result["formula_id"])
