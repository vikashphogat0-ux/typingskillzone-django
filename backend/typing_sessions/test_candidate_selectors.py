from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from exams.models import ExamConfiguration
from typing_sessions.candidate_selectors import apply_candidate_selections, selector_configuration, validate_candidate_selections


class CandidateSelectorTests(SimpleTestCase):
    def exam(self, scoring_rules):
        return ExamConfiguration(
            code="selector-test", name="Selector test", scoring_mode="CUSTOM",
            scoring_rules=scoring_rules,
        )

    def test_category_is_required_and_validated_from_configured_caps(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "normal_error_caps": {"UR": 20, "SC": 30}})
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {})
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {"candidate_category": "ADMIN"})
        self.assertEqual(
            validate_candidate_selections(exam, {"candidate_category": "SC"})["candidate_category"],
            "SC",
        )

    def test_higher_standard_requires_configured_variant_and_eligibility_attestation(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "normal_error_caps": {"UR": 20}, "profile_configuration": {
            "variants": [
                {"id": "normal", "label": "Normal standard", "standard_type": "NORMAL"},
                {"id": "higher", "label": "Higher standard post", "standard_type": "HIGHER", "requires_post_eligibility": True},
            ]
        }})
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {"candidate_category": "UR", "candidate_variant": "higher"})
        selected = validate_candidate_selections(exam, {
            "candidate_category": "UR", "candidate_variant": "higher", "eligibility_confirmed": "1",
        })
        self.assertEqual(selected["standard_type"], "HIGHER")
        self.assertEqual(selected["eligibility_status"], "CANDIDATE_ATTESTED")

    def test_invalid_variant_and_post_are_rejected(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "profile_configuration": {
            "variants": [{"id": "normal", "label": "Normal", "standard_type": "NORMAL"}],
            "post_presets": [{"id": "post_a", "label": "Post A"}],
        }})
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {"candidate_variant": "forged", "candidate_post": "post_a"})
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {"candidate_variant": "normal", "candidate_post": "forged"})

    def test_snapshot_applies_standard_without_mutating_profile_rules(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "standard_type": "NORMAL"})
        original = dict(exam.scoring_rules)
        snapshot = apply_candidate_selections({"scoring_rules": exam.scoring_rules}, {"standard_type": "HIGHER"})
        self.assertEqual(snapshot["scoring_rules"]["standard_type"], "HIGHER")
        self.assertEqual(exam.scoring_rules, original)

    def test_post_selection_required_only_for_higher_standard(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "normal_error_caps": {"UR": 20},
            "higher_error_caps": {"UR": 5}, "profile_configuration": {
                "variants": [
                    {"id": "normal", "label": "Normal", "standard_type": "NORMAL"},
                    {"id": "higher", "label": "Higher", "standard_type": "HIGHER", "requires_post_eligibility": True},
                ],
                "post_presets": [{"id": "tax_assistant", "label": "Tax Assistant", "requires_eligibility": True}],
            }})
        normal = validate_candidate_selections(exam, {"candidate_category": "UR", "candidate_variant": "normal"})
        self.assertEqual(normal["standard_type"], "NORMAL")
        with self.assertRaises(ValidationError):
            validate_candidate_selections(exam, {"candidate_category": "UR", "candidate_variant": "higher", "eligibility_confirmed": "1"})
        higher = validate_candidate_selections(exam, {
            "candidate_category": "UR", "candidate_variant": "higher",
            "candidate_post": "tax_assistant", "eligibility_confirmed": "1",
        })
        self.assertEqual(higher["post_id"], "tax_assistant")
        self.assertTrue(higher["eligibility_attested"])

    def test_selector_configuration_exposes_only_profile_declared_options(self):
        exam = self.exam({"formula": "SSC_CGL_2025_DEST", "profile_configuration": {
            "variants": [{"id": "normal", "label": "Normal"}]
        }})
        config = selector_configuration(exam)
        self.assertEqual([item["id"] for item in config["variants"]], ["normal"])
        self.assertEqual(config["categories"], [])
