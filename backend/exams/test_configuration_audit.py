from django.test import SimpleTestCase

from exams.configuration_audit import audit_exam_configuration
from exams.models import ExamConfiguration


class ExistingConfigurationAuditTests(SimpleTestCase):
    def test_unconfigured_legacy_profile_is_not_reported_ready(self):
        exam = ExamConfiguration(
            code="draft-profile",
            name="Draft profile",
            language="HINDI",
            scoring_mode=ExamConfiguration.ScoringMode.GENERIC,
        )
        result = audit_exam_configuration(exam)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "DRAFT_INCOMPLETE")
        self.assertTrue(any("duration" in message.lower() for message in result["errors"]))
        self.assertTrue(any("keyboard layout" in message.lower() for message in result["errors"]))

    def test_error_percentage_requires_denominator(self):
        exam = ExamConfiguration(
            code="percent-profile",
            name="Percent profile",
            duration_seconds=600,
            passage_layout=ExamConfiguration.PassageLayout.PARAGRAPHS,
            passage_source_mode=ExamConfiguration.PassageSourceMode.SCREEN,
            backspace_policy=ExamConfiguration.BackspacePolicy.FULL,
            allow_backspace=True,
            enter_behavior=ExamConfiguration.EnterBehavior.NEW_LINE,
            space_behavior=ExamConfiguration.SpaceBehavior.NORMAL,
            tab_behavior=ExamConfiguration.TabBehavior.INSERT_SPACES,
            scoring_mode=ExamConfiguration.ScoringMode.ERROR_PERCENTAGE,
            scoring_rules={"formula": "error_percentage"},
            error_rules={"classes": {"full": [], "half": []}},
            qualification_rules={"criteria": [{"field": "error_percentage", "operator": "<=", "value": 7}]},
        )
        result = audit_exam_configuration(exam)
        self.assertIn("Error-percentage scoring requires an explicit denominator.", result["errors"])


class RulebookPipelineAuditTests(SimpleTestCase):
    def test_internal_profile_without_formula_and_criteria_is_blocked_at_each_stage(self):
        exam = ExamConfiguration(
            code="internal-draft",
            name="Internal rulebook draft",
            duration_seconds=600,
            passage_layout=ExamConfiguration.PassageLayout.PARAGRAPHS,
            passage_source_mode=ExamConfiguration.PassageSourceMode.SCREEN,
            backspace_policy=ExamConfiguration.BackspacePolicy.FULL,
            allow_backspace=True,
            enter_behavior=ExamConfiguration.EnterBehavior.NEW_LINE,
            space_behavior=ExamConfiguration.SpaceBehavior.NORMAL,
            tab_behavior=ExamConfiguration.TabBehavior.INSERT_SPACES,
            keyboard_layout="QWERTY",
            scoring_mode=ExamConfiguration.ScoringMode.CUSTOM,
            scoring_rules={"rulebook_verification": "internal"},
            qualification_rules={},
        )
        result = audit_exam_configuration(exam)
        self.assertFalse(result["ready"])
        self.assertEqual(result["stage_checks"]["scoring"]["status"], "BLOCKED")
        self.assertEqual(result["stage_checks"]["qualification"]["status"], "BLOCKED")
        self.assertEqual(result["stage_checks"]["result"]["status"], "BLOCKED")

    def test_category_qualification_requires_a_server_validated_selector(self):
        exam = ExamConfiguration(
            code="category-selector-draft",
            name="Category selector draft",
            duration_seconds=600,
            passage_layout=ExamConfiguration.PassageLayout.PARAGRAPHS,
            passage_source_mode=ExamConfiguration.PassageSourceMode.SCREEN,
            backspace_policy=ExamConfiguration.BackspacePolicy.FULL,
            allow_backspace=True,
            enter_behavior=ExamConfiguration.EnterBehavior.NEW_LINE,
            space_behavior=ExamConfiguration.SpaceBehavior.NORMAL,
            tab_behavior=ExamConfiguration.TabBehavior.INSERT_SPACES,
            keyboard_layout="QWERTY",
            scoring_mode=ExamConfiguration.ScoringMode.CUSTOM,
            scoring_rules={
                "rulebook_verification": "internal",
                "rulebook_scoring": {
                    "engine_version": 1,
                    "formula": "ERROR_PERCENT_WEIGHTED",
                    "parameters": {"denominator": "reference_words"},
                },
            },
            qualification_rules={
                "engine_version": 1,
                "mode": "ALL",
                "criteria": [{
                    "id": "category_error_cap",
                    "metric": "error_percent",
                    "operator": "lte",
                    "value": None,
                    "category_values": {"UR": 7, "OBC": 10},
                }],
            },
        )
        result = audit_exam_configuration(exam)
        self.assertFalse(result["ready"])
        self.assertTrue(any("server-validated candidate-category selector" in message for message in result["errors"]))
