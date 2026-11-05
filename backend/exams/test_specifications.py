import json
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from exams.models import ExamConfiguration
from exams.specifications import (
    SPECIFICATION_SCHEMA_VERSION,
    resolve_exam_specification,
)


class ExamSpecificationResolverTests(SimpleTestCase):
    def test_resolver_projects_legacy_profile_without_mutating_it(self):
        exam = ExamConfiguration(
            code="delhi-police-hcm-en",
            name="Delhi Police HCM English",
            language="ENGLISH",
            script="LATIN",
            duration_seconds=600,
            minimum_wpm=Decimal("30.00"),
            passage_word_limit=400,
            allow_backspace=False,
            backspace_policy="NOT_SPECIFIED",
            verification_status="UNVERIFIED",
        )

        resolved = resolve_exam_specification(exam)

        self.assertEqual(resolved["specification_schema_version"], SPECIFICATION_SCHEMA_VERSION)
        self.assertEqual(resolved["identity"]["code"], "delhi-police-hcm-en")
        self.assertEqual(resolved["timing"]["duration_seconds"], 600)
        self.assertEqual(resolved["scoring"]["minimum_wpm"], "30.00")
        self.assertEqual(resolved["passage"]["quantity"]["legacy_word_limit"], 400)
        self.assertEqual(resolved["passage"]["quantity"]["constraint"], "UNSPECIFIED")
        self.assertFalse(resolved["input_policy"]["backspace"]["legacy_allowed"])
        self.assertEqual(resolved["input_policy"]["backspace"]["policy"], "NOT_SPECIFIED")
        self.assertEqual(exam.allow_backspace, False)
        self.assertEqual(exam.backspace_policy, "NOT_SPECIFIED")

    def test_resolver_preserves_distinct_passage_presentation_dimensions(self):
        exam = ExamConfiguration(
            code="layout-sample",
            name="Layout Sample",
            passage_format="TCS",
            passage_layout="PARA_TAB",
            passage_source_mode="PRINTED",
            passage_preserve_tabs=True,
            passage_tab_size=8,
            passage_paragraph_spacing_pt=16,
            passage_first_line_indent_em=Decimal("1.5"),
        )

        resolved = resolve_exam_specification(exam)
        passage = resolved["passage"]

        self.assertEqual(passage["format"], "TCS")
        self.assertEqual(passage["layout"], "PARA_TAB")
        self.assertEqual(passage["source_mode"], "PRINTED")
        self.assertTrue(passage["typography"]["preserve_tabs"])
        self.assertEqual(passage["typography"]["tab_size"], 8)
        self.assertEqual(passage["typography"]["paragraph_spacing_pt"], 16)
        self.assertEqual(passage["typography"]["first_line_indent_em"], "1.5")

    def test_provenance_dates_are_iso_formatted_and_separate(self):
        exam = ExamConfiguration(
            code="provenance-sample",
            name="Provenance Sample",
            source_checked_at=date(2026, 11, 5),
            presentation_reference_checked_at=date(2026, 11, 4),
            official_source_url="https://example.com/notice",
            source_title="Official notice",
            presentation_reference_url="https://example.com/reference",
            presentation_reference_title="Presentation reference",
            presentation_reference_status="REVIEWED",
        )

        resolved = resolve_exam_specification(exam)
        provenance = resolved["provenance"]

        self.assertEqual(provenance["source_checked_at"], "2026-11-05")
        self.assertEqual(
            provenance["presentation_reference"]["checked_at"], "2026-11-04"
        )
        self.assertEqual(provenance["verification_status"], "UNVERIFIED")
        self.assertEqual(
            provenance["presentation_reference"]["status"], "REVIEWED"
        )

    def test_resolved_specification_is_json_serializable(self):
        exam = ExamConfiguration(
            code="json-sample",
            name="JSON Sample",
            minimum_wpm=Decimal("25.50"),
            error_allowance_percent=Decimal("5.00"),
            scoring_rules={"score_bands": [[25, 10]]},
        )

        resolved = resolve_exam_specification(exam)
        encoded = json.dumps(resolved)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["scoring"]["minimum_wpm"], "25.50")
        self.assertEqual(decoded["scoring"]["error_allowance_percent"], "5.00")
        self.assertEqual(decoded["scoring"]["scoring_rules"]["score_bands"], [[25, 10]])

    def test_resolver_does_not_invent_missing_duration_or_verification(self):
        exam = ExamConfiguration(code="unverified-sample", name="Unverified Sample")

        resolved = resolve_exam_specification(exam)

        self.assertIsNone(resolved["timing"]["duration_seconds"])
        self.assertEqual(resolved["provenance"]["verification_status"], "UNVERIFIED")
        self.assertEqual(resolved["scoring"]["error_rules"], {})
        self.assertEqual(resolved["scoring"]["scoring_rules"], {})
        self.assertEqual(resolved["scoring"]["qualification_rules"], {})
