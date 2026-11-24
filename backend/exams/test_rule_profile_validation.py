from django.test import SimpleTestCase

from .rule_profile_validation import profile_readiness, validate_rule_profile


def complete_profile():
    return {
        "schema_version": 1,
        "identity": {"profile_id": "ssc-chsl-en-2025", "exam_name": "SSC CHSL 2025", "language": "ENGLISH", "script": "LATIN"},
        "timing": {"duration_seconds": 600},
        "interaction": {
            "backspace": "FULL", "allow_backspace": True, "delete": True,
            "paste": False, "copy": False, "cut": False, "arrow_navigation": True,
            "enter": "NEW_LINE", "space": "NORMAL", "tab": "INSERT_SPACES",
        },
        "passage": {
            "source_mode": "SCREEN", "format": "PARAGRAPHS", "layout": "PARAGRAPHS",
            "font_family": "Arial", "font_size_pt": 12, "alignment": "LEFT",
        },
        "scoring": {
            "mode": "FULL_HALF_MISTAKES", "formula": {"expression": "(full + 0.5 * half) / attempted_words"},
            "error_rules": {"classes": {"full": ["omission", "substitution"], "half": ["spacing", "punctuation"]}},
        },
        "qualification": {
            "criteria": [{"field": "error_percentage", "operator": "<=", "value": 7}],
            "outcome_labels": {"qualified": "QUALIFIED", "not_qualified": "NOT QUALIFIED"},
        },
        "provenance": {"source_document": "Master_Exam_Rulebook_Typing_DEST.docx", "officially_verified": False},
    }


class RuleProfileValidationTests(SimpleTestCase):
    def test_complete_profile_is_ready_but_unverified_warning_is_retained(self):
        audit = validate_rule_profile(complete_profile())
        self.assertTrue(audit["ready"])
        self.assertTrue(any("not marked as verified" in item for item in audit["warnings"]))

    def test_missing_fields_are_not_inferred(self):
        profile = complete_profile()
        del profile["interaction"]["tab"]
        audit = validate_rule_profile(profile)
        self.assertFalse(audit["ready"])
        self.assertIn("interaction.tab must be explicitly configured", audit["errors"])

    def test_backspace_conflict_blocks_readiness(self):
        profile = complete_profile()
        profile["interaction"]["backspace"] = "DISABLED"
        audit = validate_rule_profile(profile)
        self.assertFalse(audit["ready"])
        self.assertTrue(any("conflicts" in item for item in audit["errors"]))

    def test_scoring_mode_requires_its_denominator_or_penalty(self):
        profile = complete_profile()
        profile["scoring"]["mode"] = "ERROR_PERCENTAGE"
        audit = validate_rule_profile(profile)
        self.assertIn("scoring.error_denominator is required for ERROR_PERCENTAGE", audit["errors"])

    def test_notification_dependent_profile_is_explicitly_flagged(self):
        profile = complete_profile()
        profile["provenance"]["notification_dependent"] = True
        result = profile_readiness(profile)
        self.assertEqual(result["status"], "READY")
        self.assertGreater(result["warning_count"], 0)
