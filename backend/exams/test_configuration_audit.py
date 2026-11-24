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
