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
        self.assertEqual(result["stage_checks"]["result_and_audit"]["status"], "BLOCKED")

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


class SevenStagePipelineAuditTests(SimpleTestCase):
    def test_audit_exposes_exactly_seven_release_stages(self):
        exam = ExamConfiguration(
            code="seven-stage-profile",
            name="Seven stage profile",
            language="ENGLISH",
            script="LATIN",
            duration_seconds=600,
            passage_format=ExamConfiguration.PassageFormat.TCS,
            passage_layout=ExamConfiguration.PassageLayout.TCS,
            passage_source_mode=ExamConfiguration.PassageSourceMode.SCREEN,
            backspace_policy=ExamConfiguration.BackspacePolicy.FULL,
            allow_backspace=True,
            allow_delete=True,
            allow_arrow_navigation=True,
            allow_copy=False,
            allow_paste=False,
            allow_cut=False,
            enter_behavior=ExamConfiguration.EnterBehavior.NEW_LINE,
            space_behavior=ExamConfiguration.SpaceBehavior.NORMAL,
            tab_behavior=ExamConfiguration.TabBehavior.INSERT_SPACES,
            keyboard_layout="QWERTY",
            presentation_reference_status=ExamConfiguration.PresentationReferenceStatus.VERIFIED,
            scoring_mode=ExamConfiguration.ScoringMode.CUSTOM,
            scoring_rules={
                "recruitment_cycle": "2025",
                "profile_configuration": {"source_profile_id": "ssc-chsl-en-2025", "category_selector": "candidate_category"},
                "rulebook_scoring": {
                    "engine_version": 1, "formula": "ERROR_PERCENT_WEIGHTED",
                    "parameters": {"denominator": "reference_words"},
                },
            },
            error_rules={"classes": {"full": ["omission"], "half": ["punctuation"]}},
            qualification_rules={
                "engine_version": 1, "mode": "ALL",
                "criteria": [{"id": "speed", "metric": "net_wpm", "operator": "gte", "value": 35}],
            },
        )
        result = audit_exam_configuration(exam)
        self.assertEqual(
            set(result["stage_checks"]),
            {"catalogue", "candidate_selection", "launch_and_timer", "interface_and_passage",
             "scoring", "qualification", "result_and_audit"},
        )
        self.assertEqual(result["stage_checks"]["catalogue"]["status"], "READY")
        self.assertEqual(result["stage_checks"]["scoring"]["status"], "READY")
        self.assertEqual(result["stage_checks"]["qualification"]["status"], "READY")

    def test_missing_cycle_identity_blocks_catalogue_stage(self):
        exam = ExamConfiguration(code="no-cycle", name="No cycle", language="ENGLISH", script="LATIN")
        result = audit_exam_configuration(exam)
        self.assertEqual(result["stage_checks"]["catalogue"]["status"], "BLOCKED")
        self.assertFalse(result["ready"])

    def test_selector_schema_and_duplicate_ids_block_candidate_selection(self):
        exam = ExamConfiguration(
            code="bad-selector", name="Bad selector", language="ENGLISH", script="LATIN",
            scoring_rules={"profile_configuration": {
                "variants": [{"id": "normal"}, {"id": "normal"}],
            }},
        )
        result = audit_exam_configuration(exam)
        self.assertEqual(result["stage_checks"]["candidate_selection"]["status"], "BLOCKED")
        self.assertTrue(any("duplicate ids" in message for message in result["errors"]))

    def test_unverified_presentation_reference_blocks_interface_stage(self):
        exam = ExamConfiguration(
            code="presentation-pending", name="Presentation pending",
            language="ENGLISH", script="LATIN", duration_seconds=600,
            passage_format=ExamConfiguration.PassageFormat.TCS,
            passage_layout=ExamConfiguration.PassageLayout.TCS,
            passage_source_mode=ExamConfiguration.PassageSourceMode.SCREEN,
            backspace_policy=ExamConfiguration.BackspacePolicy.FULL, allow_backspace=True,
            enter_behavior=ExamConfiguration.EnterBehavior.NEW_LINE,
            space_behavior=ExamConfiguration.SpaceBehavior.NORMAL,
            tab_behavior=ExamConfiguration.TabBehavior.INSERT_SPACES,
            keyboard_layout="QWERTY",
        )
        result = audit_exam_configuration(exam)
        self.assertEqual(result["stage_checks"]["interface_and_passage"]["status"], "BLOCKED")


    def test_result_stage_checks_real_result_template_and_contract_fields(self):
        exam = ExamConfiguration(code="result-contract", name="Result contract", language="ENGLISH", script="LATIN")
        result = audit_exam_configuration(exam)
        checks = result["stage_checks"]["result_and_audit"]["checks"]
        self.assertTrue(checks["result_template_exists"])
        self.assertTrue(checks["formula_status_contract"])
        self.assertTrue(checks["qualification_status_contract"])
        self.assertTrue(checks["qualification_breakdown_contract"])
        self.assertTrue(checks["formula_metrics_contract"])
